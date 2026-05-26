"""Resolve the four knowledge fingerprints stamped on every NL audit row.

T-002 introduces ``prompt_version`` / ``glossary_version`` /
``schema_snapshot_id`` / ``exemplar_set_hash`` on ``KpiNlRun`` and
``KpiChatMessage``. This module is the single resolver every writer
calls so the values are computed identically across surfaces (editor
NL generate, chat turn, eval runner) and across phases.

Resolution order:

* **prompt_version**     env ``KPI_PROMPT_VERSION`` → KpiSettings.prompt_version
                         (future column, currently unset) → fallback ``"0.0.0"``.
                         The convention is semver: bump MAJOR for breaking
                         system-prompt rewrites, MINOR for behavioural tweaks,
                         PATCH for typo/wording fixes.
* **glossary_version**   ``None`` until T-301 (structured glossary) lands.
                         Then: monotonic counter that bumps on every glossary
                         term mutation.
* **schema_snapshot_id** Resolved from ``introspector.get_current_snapshot``
                         on every call — cheap (single indexed SELECT).
* **exemplar_set_hash**  ``None`` until T-401 (exemplar bank) lands. Then:
                         sha256 of sorted ``(exemplar_id, updated_at)`` pairs
                         of every exemplar that contributed to the prompt.

Pre-T-301 / T-401, the unset fields are ``None`` and the writer simply
leaves the columns NULL. That's the right shape: a NULL in a fingerprint
column says "the relevant knowledge layer wasn't a factor on this run."
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from kpi_studio.services import introspector


DEFAULT_PROMPT_VERSION = "0.0.0"


@dataclass(frozen=True)
class KnowledgeFingerprint:
    """The four columns to stamp on every new NL audit row."""
    prompt_version: Optional[str]
    glossary_version: Optional[str]
    schema_snapshot_id: Optional[int]
    exemplar_set_hash: Optional[str]

    def as_kwargs(self) -> dict:
        """Spread into a model constructor: ``KpiNlRun(..., **fp.as_kwargs())``."""
        return {
            "prompt_version": self.prompt_version,
            "glossary_version": self.glossary_version,
            "schema_snapshot_id": self.schema_snapshot_id,
            "exemplar_set_hash": self.exemplar_set_hash,
        }


def current(db: Session) -> KnowledgeFingerprint:
    """Resolve every fingerprint field for *this* request.

    Cheap: at most one indexed SELECT (the snapshot lookup). Safe to
    call once per audit-row insert without performance worry.
    """
    return KnowledgeFingerprint(
        prompt_version=_resolve_prompt_version(),
        glossary_version=_resolve_glossary_version(db),
        schema_snapshot_id=_resolve_schema_snapshot_id(db),
        exemplar_set_hash=_resolve_exemplar_set_hash(db),
    )


# ---------------------------------------------------------------------------
# Individual resolvers — kept separate so each can be unit-tested without
# touching the others and so the swap-in points for T-301 / T-401 are
# obvious.
# ---------------------------------------------------------------------------

def _resolve_prompt_version() -> str:
    """Read the system-prompt's semantic version from env.

    Convention: every change to the agent / preflight system prompt
    bumps this. Until the deploy pipeline starts setting it, the
    fallback ``"0.0.0"`` makes pre-T-002 rows distinguishable from
    intentionally-versioned ones.
    """
    v = os.environ.get("KPI_PROMPT_VERSION") or ""
    return v.strip() or DEFAULT_PROMPT_VERSION


def _resolve_glossary_version(_db: Session) -> Optional[str]:
    """Glossary version. ``None`` until T-301 ships the
    ``kpi_glossary_term`` table; then this becomes a SELECT of the
    monotonic counter the glossary CRUD endpoints bump."""
    return None


def _resolve_schema_snapshot_id(db: Session) -> Optional[int]:
    """ID of the snapshot the agent saw on this turn. Reads the
    ``is_current=True`` row; ``None`` if nothing has been introspected
    yet (fresh install)."""
    snap = introspector.get_current_snapshot(db)
    return snap.snapshot_id if snap is not None else None


def _resolve_exemplar_set_hash(_db: Session) -> Optional[str]:
    """Exemplar bank fingerprint. ``None`` until T-401 ships the
    ``kpi_query_exemplar`` table; then this becomes a hash of the
    (sorted) exemplar IDs + their updated_at timestamps."""
    return None
