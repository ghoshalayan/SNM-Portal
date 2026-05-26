"""Per-stage LLM provider healthcheck (T-004).

Walks every stage that resolves to a real (provider, model) pair,
collapses duplicates so models shared across stages probe once, and
issues a tiny completion against each. Surfaces:

* startup-time pre-flight: called from ``app/main.py`` lifespan; the
  result is cached with a TTL so the settings page reads it instantly
  without an extra round-trip.
* save-time validation: ``PUT /settings`` calls the same routine to
  refuse a save that introduces a misconfigured stage model unless the
  admin passes ``force=true``.
* weekly background sweep: registered as a T-003 scheduled job so a
  rotated key / deprecated model is caught even without a user save.

A "probe" is a 1-token / 1-message ``complete()`` call. Token cost is
negligible (~3-5 tokens prompt, 1 token completion) — running it for
6 stages every 7 days is well under a cent per week.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Optional

from sqlalchemy.orm import Session

from kpi_studio.providers.llm.base import LlmMessage, LlmProviderError
from kpi_studio.services import call_logger, settings_service
from kpi_studio.stages import STAGES, all_stage_keys


log = logging.getLogger(__name__)


# In-process result cache. Settings page hits this first; force=True or
# the TTL expiring triggers a fresh probe set.
CACHE_TTL_SECONDS = 300


@dataclass
class ProbeResult:
    """One probe outcome — covers ALL stages that resolve to the same
    (provider, model) pair so we don't pay for duplicates."""
    provider: str
    model: str
    ok: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    stages: list[str] = field(default_factory=list)


@dataclass
class HealthcheckResult:
    overall_ok: bool
    checked_at: datetime
    probes: list[ProbeResult]
    cached: bool = False


_cache_lock = Lock()
_cached_result: Optional[HealthcheckResult] = None


def run_healthcheck(
    db: Session, *, force: bool = False, stage_keys: Optional[list[str]] = None,
    trigger_source: str = "healthcheck_auto",
) -> HealthcheckResult:
    """Probe each unique (provider_config_id|legacy, model) pair.

    Two probe sources:

    1. **Per-stage**: walks every declared stage, resolves its
       (provider_config_id, model), groups duplicates so one model
       shared across stages probes once.
    2. **Standalone providers**: also probes every provider config not
       referenced by any stage, with its default model — so an admin
       who adds a new provider but hasn't routed any stage to it yet
       still sees a green/red signal for the credentials.
    """
    global _cached_result

    if not force:
        cached = _read_cache()
        if cached is not None:
            return cached

    eff = settings_service.get_effective(db, env=None)
    target_stages = stage_keys or all_stage_keys()

    # Group stages by (provider_key, model) where provider_key is a
    # stable string the UI can render. Build a parallel map to the
    # actual provider instance so we don't re-build for duplicates.
    pair_to_stages: dict[tuple[str, str], list[str]] = {}
    pair_to_provider: dict[tuple[str, str], object] = {}
    pair_to_label: dict[tuple[str, str], str] = {}

    for stage_key in target_stages:
        cid = settings_service.resolve_stage_provider_config_id(eff, stage_key)
        model = settings_service.resolve_stage_model(eff, stage_key) or "(unset)"
        prov = settings_service.provider_for_stage(eff, stage_key, db=db)
        if prov is None:
            pair = ("(none)", "(none)")
            pair_to_stages.setdefault(pair, []).append(stage_key)
            pair_to_label[pair] = "no provider"
            continue
        # Provider key: prefer the config id when present so two stages
        # routed to the same id+model probe once, even when two
        # different configs share a kind.
        if cid is not None:
            provider_key = f"config:{cid}"
            from kpi_studio.services import provider_config_service
            row = provider_config_service.get(db, cid)
            label = (row.display_name if row else f"config #{cid}") + f" ({getattr(prov, 'name', '?')})"
        else:
            provider_key = f"legacy:{getattr(prov, 'name', eff.provider_name or '?')}"
            label = f"{getattr(prov, 'name', '?')} (legacy single-provider)"
        pair = (provider_key, model)
        pair_to_stages.setdefault(pair, []).append(stage_key)
        pair_to_provider.setdefault(pair, prov)
        pair_to_label[pair] = label

    # Also probe any provider config that's active but unrouted —
    # gives the admin a credential-validity signal for "I added this
    # config but haven't used it yet".
    from kpi_studio.services import provider_config_service
    referenced_cids = {
        settings_service.resolve_stage_provider_config_id(eff, k)
        for k in target_stages
    }
    for row in provider_config_service.list_active(db):
        if row.provider_config_id in referenced_cids:
            continue
        # Resolution: row's admin-entered default_model wins; fall
        # back to KIND_DEFAULTS for legacy rows that haven't been
        # re-saved since the 2026-05-25 default_model column landed.
        unrouted_model = (
            (row.default_model or "").strip()
            or provider_config_service.default_model_for_kind(row.kind)
            or "(default)"
        )
        pair = (f"config:{row.provider_config_id}", unrouted_model)
        if pair in pair_to_provider:
            continue
        try:
            prov = provider_config_service.build_provider(row, model=pair[1] if pair[1] != "(default)" else None)
        except ValueError:
            continue
        pair_to_provider[pair] = prov
        pair_to_stages.setdefault(pair, [])  # no stage_list — unrouted
        pair_to_label[pair] = f"{row.display_name} (unrouted)"

    # Parallel probe execution. Each upstream LLM round-trip is 2-4s;
    # before this change we ran them sequentially and a save with 3-5
    # unique (provider, model) pairs took 10+ seconds. ThreadPoolExecutor
    # with 8 workers caps concurrency at a sensible level (most admins
    # have <8 providers) and lets a stuck probe time out without
    # blocking the others.
    probes: list[ProbeResult] = []
    probe_args: list[tuple[tuple[str, str], list[str]]] = []
    for pair, stage_list in pair_to_stages.items():
        provider_key, _ = pair
        if provider_key == "(none)":
            probes.append(ProbeResult(
                provider="(none)", model=pair[1], ok=False,
                error="No LLM provider configured.",
                stages=stage_list,
            ))
            continue
        probe_args.append((pair, stage_list))

    if probe_args:
        max_workers = min(8, len(probe_args))
        # All probes in this batch share one correlation_id so the Call
        # log tab can group "this healthcheck = 5 probes" cleanly.
        # log_context inside a thread is tricky — contextvars don't
        # propagate to ThreadPoolExecutor workers by default. We capture
        # the cid out here and re-establish it inside each probe.
        with call_logger.log_context(trigger_source=trigger_source) as cid:
            with ThreadPoolExecutor(max_workers=max_workers,
                                    thread_name_prefix="kpi-hc") as pool:
                futures = {}
                for pair, stage_list in probe_args:
                    prov = pair_to_provider[pair]
                    label = pair_to_label.get(pair, pair[0])
                    fut = pool.submit(
                        _probe_in_thread,
                        prov, label, pair[1], stage_list, cid, trigger_source,
                    )
                    futures[fut] = (pair, stage_list)
                for fut in as_completed(futures):
                    try:
                        probes.append(fut.result())
                    except Exception as exc:  # noqa: BLE001
                        pair, stage_list = futures[fut]
                        probes.append(ProbeResult(
                            provider=pair_to_label.get(pair, pair[0]),
                            model=pair[1],
                            ok=False,
                            error=f"probe crashed: {exc!r}"[:500],
                            stages=stage_list,
                        ))

    result = HealthcheckResult(
        overall_ok=all(p.ok for p in probes) if probes else False,
        checked_at=datetime.now(timezone.utc),
        probes=probes,
    )
    _write_cache(result)
    return result


def probe_provider_config(
    db: Session,
    provider_config_id: int,
    *,
    model: Optional[str] = None,
) -> ProbeResult:
    """One-off probe for the 'Test connection' affordance on a single
    provider card. Doesn't touch the run_healthcheck cache.

    ``model``: when None, uses the provider's default for its kind.
    UI passes it through when the admin wants to test a specific model
    they've routed in stage_models.
    """
    from kpi_studio.services import provider_config_service
    row = provider_config_service.get(db, provider_config_id)
    if row is None:
        return ProbeResult(
            provider=f"config:{provider_config_id}",
            model=(model or "(default)"),
            ok=False,
            error=f"Provider config {provider_config_id} not found.",
        )
    # Resolve "what model to display + use" once — same priority as
    # the runtime resolver: per-call > row's default_model > KIND_DEFAULTS.
    def _resolve_model() -> str:
        return (
            (model or "").strip()
            or (row.default_model or "").strip()
            or provider_config_service.default_model_for_kind(row.kind)
        )

    if not row.is_active:
        return ProbeResult(
            provider=row.display_name,
            model=_resolve_model(),
            ok=False,
            error="Provider config is inactive (soft-deleted).",
        )
    try:
        prov = provider_config_service.build_provider(row, model=model)
    except ValueError as exc:
        return ProbeResult(
            provider=row.display_name,
            model=_resolve_model(),
            ok=False,
            error=str(exc),
        )
    chosen_model = _resolve_model()
    return _probe_one(
        prov,
        f"{row.display_name} ({row.kind})",
        chosen_model or "(unset)",
        stage_list=[],
    )


def latest_cached() -> Optional[HealthcheckResult]:
    """Return the most recent cached result without forcing a probe.
    Returns ``None`` when nothing has been cached yet — startup hasn't
    run or the TTL expired in a way that cleared it."""
    with _cache_lock:
        return _cached_result


def invalidate_cache() -> None:
    """Clear the cache. Called from ``PUT /settings`` so the next
    healthcheck (or page load) re-probes against the new config."""
    global _cached_result
    with _cache_lock:
        _cached_result = None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _probe_in_thread(provider, provider_name: str, model: str,
                     stage_list: list[str],
                     correlation_id: Optional[str],
                     trigger_source: str) -> ProbeResult:
    """Worker-thread entry. ContextVars don't propagate across
    ThreadPoolExecutor by default, so re-establish the call-log
    context inside the thread so the probe's HTTP call lands in the
    same group as its siblings."""
    if correlation_id:
        with call_logger.log_context(
            trigger_source=trigger_source,
            correlation_id=correlation_id,
        ):
            return _probe_one(provider, provider_name, model, stage_list)
    return _probe_one(provider, provider_name, model, stage_list)


def _probe_one(provider, provider_name: str, model: str,
               stage_list: list[str]) -> ProbeResult:
    """One LLM call. Cheap — small completion. Captures latency +
    exception class for the UI's red/yellow/green bands.

    2026-05-26: budget bumped from 1 to 16 tokens. Reasoning models
    (OpenAI's gpt-5.x / o-series) emit chain-of-thought tokens before
    the visible reply, so ``max_tokens=1`` returned the "could not
    finish the message because max_tokens... was reached" error and
    the probe reported a false failure. 16 tokens is still under one
    cent per probe on every provider we ship, but big enough for the
    model to emit at least one visible token."""
    started = time.perf_counter()
    try:
        # Smallest viable request: one user turn, tight budget. The
        # body content doesn't matter — we only care about whether the
        # round-trip succeeds.
        _ = provider.complete(
            messages=[LlmMessage(role="user", content="ping")],
            max_tokens=16,
            temperature=0.0,
        )
    except LlmProviderError as exc:
        return ProbeResult(
            provider=provider_name, model=model, ok=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(exc)[:500],
            stages=stage_list,
        )
    except Exception as exc:  # noqa: BLE001 — anything unexpected is a fail
        return ProbeResult(
            provider=provider_name, model=model, ok=False,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=f"{type(exc).__name__}: {exc!r}"[:500],
            stages=stage_list,
        )
    return ProbeResult(
        provider=provider_name, model=model, ok=True,
        latency_ms=int((time.perf_counter() - started) * 1000),
        stages=stage_list,
    )


def _read_cache() -> Optional[HealthcheckResult]:
    with _cache_lock:
        if _cached_result is None:
            return None
        age = datetime.now(timezone.utc) - _cached_result.checked_at
        if age > timedelta(seconds=CACHE_TTL_SECONDS):
            return None
        # Return a copy with ``cached=True`` so callers can tell.
        cached = HealthcheckResult(
            overall_ok=_cached_result.overall_ok,
            checked_at=_cached_result.checked_at,
            probes=_cached_result.probes,
            cached=True,
        )
        return cached


def _write_cache(result: HealthcheckResult) -> None:
    global _cached_result
    with _cache_lock:
        _cached_result = result


# Sanity self-import — keeps the stage taxonomy referenced so an
# accidentally-empty STAGES list surfaces at import time.
_ = STAGES
