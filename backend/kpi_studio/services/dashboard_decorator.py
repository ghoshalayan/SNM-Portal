"""Dashboard decorator — Phase J.2: AI proposes a tidy layout for an
existing dashboard.

Given the dashboard's current items (each with its KPI's chart type and
name), the LLM is asked to return per-item ``size_class`` + grid
coordinates and an optional ``title_override``. The proposal is then
validated (item_ids must exist, coords must fit a 24-col grid, no two
tiles overlap) and a fallback packer fills any gaps.

Unlike the KPI suggester, this service NEVER changes the underlying
KPI — chart type stays whatever the author chose. We only change the
*placement* of cards on the dashboard, plus the per-card title
override.

Failure modes mirror ``kpi_suggester``: provider errors and parse
errors degrade silently — the caller gets back ``items=[]`` and an
``error`` string so the editor can show "AI couldn't propose a layout".
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError,
)
from kpi_studio.schemas import BuilderFilter, BuilderSpec

log = logging.getLogger(__name__)


# 24-col grid (matches the frontend / dashboards API constants).
_GRID_COLS = 24
_VALID_ANIMATIONS = ("fade", "slide", "scale", "none")
# Curated Material icon vocabulary the LLM is allowed to choose from.
# Restricting the set keeps the proposal predictable (the frontend
# bundle ships the Material font, so any icon here is guaranteed to
# render). Maps roughly to chart-type vibes — totals get a sigma /
# trending-up, breakdowns get pie / bar etc.
_VALID_ICONS = (
    "trending_up", "trending_down", "trending_flat",
    "show_chart", "stacked_line_chart", "area_chart",
    "bar_chart", "pie_chart", "donut_large",
    "table_chart", "leaderboard", "insights",
    "calculate", "summarize", "functions",
    "shopping_cart", "attach_money", "payments", "receipt_long",
    "people", "groups", "person_pin",
    "factory", "inventory_2", "local_shipping",
    "schedule", "today", "event_available",
    "warning_amber", "check_circle", "error_outline",
    "speed", "bolt", "star",
)
_MAX_ITEMS_IN_PROMPT = 40
_MAX_FILTERS_PER_ITEM = 3


_SYSTEM_PROMPT = """\
You are a visual stylist for Power BI–style dashboards. The user has
ALREADY arranged their cards on the grid — your job is NOT to move
them. Leave every card's grid_x, grid_y, grid_w, grid_h and
size_class exactly as the input provides. Only propose VISUAL polish
(icon, entry/exit animations) and OPTIONAL per-card filters.

DO NOT:
  * change grid_x, grid_y, grid_w, grid_h
  * change size_class
  * compact, re-pack, or reorder the layout
  * try to "tidy up" the placement

DO:
  * pick a fitting Material icon from the allowed list (totals →
    trending_up / summarize; breakdowns → bar_chart / pie_chart;
    tables → table_chart; money → attach_money / payments;
    people → people / groups; etc.)
  * pick one of fade / slide / scale / none for animation_in and
    animation_out — prefer ``fade`` for calm tiles, ``slide`` for
    tables, ``scale`` for emphasis (a hero scorecard).
  * propose a short ``title_override`` (max 60 chars) ONLY when the
    kpi_name is verbose; otherwise omit it.
  * propose ``x_label`` / ``y_label`` ONLY for chart_types ``bar`` and
    ``line`` (they're ignored for scorecard / pie / table / stat_group).
    Keep them short (max 30 chars) and human-readable — e.g. for a bar
    chart of "Sales by Region", x_label="Region", y_label="Sales (₹)".
    Omit them entirely if the bar is self-explanatory or if the
    column-derived defaults already read fine.

Filter induction (optional, max 3 per card, omit when unsure):
  * Only propose filters whose ``column`` exists on the KPI's
    BuilderSpec source (listed under ``filterable_columns``). Never
    invent a column.
  * Use these ops only: ``=``, ``!=``, ``in``, ``not_in``, ``>``,
    ``>=``, ``<``, ``<=``, ``is_null``, ``is_not_null``.
  * Filters help when one card on the dashboard should show a *slice*
    (e.g. "North region only", "active customers"). If the dashboard
    looks like one cohesive view, omit filters entirely.

Allowed icons (pick exactly one, or null):
{icons}

Respond with ONE JSON object:
  {{
    "items": [
      {{
        "item_id": <int>,
        "title_override": "<optional short title or null>",
        "icon": "<one of the allowed icons or null>",
        "animation_in": "fade" | "slide" | "scale" | "none",
        "animation_out": "fade" | "slide" | "scale" | "none",
        "x_label": "<optional short axis title or null — bar/line only>",
        "y_label": "<optional short axis title or null — bar/line only>",
        "extra_filters": [
          {{ "column": "...", "op": "=", "value": "..." }}
        ]
      }},
      ...
    ]
  }}

No prose. No code fences. Every dashboard item MUST appear exactly
once. Item_ids MUST match the input. The backend will discard any
grid_* / size_class fields you include, so don't bother emitting them.
""".format(icons=", ".join(_VALID_ICONS))


@dataclass
class ItemPlacement:
    """One item's proposed placement after validation."""
    item_id: int
    grid_x: int
    grid_y: int
    grid_w: int
    grid_h: int
    size_class: str
    title_override: Optional[str] = None
    # Phase J.2 — per-card visual + filter polish.
    icon: Optional[str] = None
    animation_in: Optional[str] = None
    animation_out: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    extra_filters: List[BuilderFilter] = field(default_factory=list)


@dataclass
class DecorationResult:
    items: List[ItemPlacement] = field(default_factory=list)
    tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    error: Optional[str] = None
    used_fallback: bool = False
    """True when the LLM's proposal couldn't be used (parse error,
    provider error, all items dropped) and we fell back to a
    rule-based packer instead. The frontend can still apply this —
    it's a sensible default arrangement — but it should label the
    result as "auto-packed" rather than "AI suggestion"."""


@dataclass
class DashboardItemView:
    """Trimmed view of a dashboard item — what we feed the LLM and
    what we use to backfill missing fields."""
    item_id: int
    kpi_id: int
    kpi_name: str
    chart_type: str
    grid_x: int
    grid_y: int
    grid_w: int
    grid_h: int
    size_class: str
    title_override: Optional[str] = None
    # Phase J.2 — present so AI Polish can preserve / replace these.
    icon: Optional[str] = None
    animation_in: Optional[str] = None
    animation_out: Optional[str] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    extra_filters: List[BuilderFilter] = field(default_factory=list)
    # Optional saved BuilderSpec — when present, gives the LLM the
    # source table + columns it can safely propose filters against.
    # Raw-SQL KPIs have no spec, so the prompt will omit
    # ``filterable_columns`` for them and the LLM will skip filters.
    builder_spec: Optional[BuilderSpec] = None


def decorate_dashboard(
    *,
    provider: LlmProvider,
    items: List[DashboardItemView],
    dashboard_name: str = "",
    max_tokens: int = 3000,
) -> DecorationResult:
    """Ask the LLM for a tidier layout. Always returns a
    ``DecorationResult`` — the items list is empty only if there were
    no items to begin with. Provider/parse failures fall back to a
    rule-based packer that still produces a usable layout."""
    if not items:
        return DecorationResult()

    # Cap input — a dashboard with hundreds of cards is pathological,
    # and we don't want to blow up the prompt.
    trimmed = items[:_MAX_ITEMS_IN_PROMPT]

    payload = _build_user_payload(trimmed, dashboard_name)
    messages = [
        LlmMessage(role="system", content=_SYSTEM_PROMPT),
        LlmMessage(role="user", content=payload),
    ]

    started = time.perf_counter()
    try:
        completion = provider.complete(
            messages,
            json_mode=True,
            max_tokens=max_tokens,
            temperature=0.2,
        )
    except LlmProviderError as exc:
        log.warning("kpi_studio.decorator: provider error: %s", exc)
        return DecorationResult(
            items=_fallback_pack(trimmed),
            error=f"provider_error: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
            used_fallback=True,
        )

    parsed = _parse_response(completion.text)
    if parsed is None:
        log.info(
            "kpi_studio.decorator: model returned non-JSON: %r",
            (completion.text or "")[:300],
        )
        return DecorationResult(
            items=_fallback_pack(trimmed),
            error="parse_error",
            tokens=int(completion.usage.get("total_tokens") or 0),
            latency_ms=completion.latency_ms,
            model=completion.model,
            used_fallback=True,
        )

    placements = _validate_placements(parsed, trimmed)
    if not placements:
        return DecorationResult(
            items=_fallback_pack(trimmed),
            error="no_valid_placements",
            tokens=int(completion.usage.get("total_tokens") or 0),
            latency_ms=completion.latency_ms,
            model=completion.model,
            used_fallback=True,
        )

    return DecorationResult(
        items=placements,
        tokens=int(completion.usage.get("total_tokens") or 0),
        latency_ms=completion.latency_ms,
        model=completion.model,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_user_payload(
    items: List[DashboardItemView], dashboard_name: str,
) -> str:
    body = {
        "dashboard_name": dashboard_name,
        "grid_columns": _GRID_COLS,
        "items": [_view_to_prompt_dict(it) for it in items],
    }
    return json.dumps(body, default=str, ensure_ascii=False)


def _view_to_prompt_dict(it: DashboardItemView) -> dict:
    """One item, in the shape the system prompt's contract expects.

    ``filterable_columns`` is the list of columns the LLM is allowed
    to filter against — only the source table's columns. Related-table
    columns are excluded because filter induction across joins is
    surprising and easy to get wrong (the compiler has to introduce
    the JOIN, and the user's intent is unclear)."""
    out: dict = {
        "item_id": it.item_id,
        "kpi_name": it.kpi_name,
        "chart_type": it.chart_type,
        "current": {
            "grid_x": it.grid_x, "grid_y": it.grid_y,
            "grid_w": it.grid_w, "grid_h": it.grid_h,
            "size_class": it.size_class,
            "title_override": it.title_override,
            "icon": it.icon,
            "animation_in": it.animation_in,
            "animation_out": it.animation_out,
            "x_label": it.x_label,
            "y_label": it.y_label,
            "extra_filters": [
                f.model_dump(by_alias=True) for f in (it.extra_filters or [])
            ],
        },
    }
    spec = it.builder_spec
    if spec is not None:
        out["source"] = {
            "schema": spec.source.schema_name,
            "name": spec.source.name,
        }
        # Pull the source table's columns out of the spec's known
        # fields. If the spec has no derived/wells columns yet (rare),
        # we omit filterable_columns and the LLM will skip filters
        # rather than guess.
        cols = _filterable_column_names(spec)
        if cols:
            out["filterable_columns"] = cols
    return out


def _filterable_column_names(spec: BuilderSpec) -> List[str]:
    """Best-effort: collect every column the BuilderSpec mentions on
    its source table. Only names from raw wells (axis / value /
    columns) and existing filters are included — derived columns are
    omitted because they live in a CTE the LLM doesn't see.

    ``wells`` is a free-form dict on BuilderSpec (the chart-type-specific
    keys vary), so we walk every list-valued well rather than naming
    them. Each entry is a BuilderField with .column / .table.
    """
    seen: set[str] = set()
    out: List[str] = []
    source_name = spec.source.name

    def _add(col: Optional[str], table: Optional[str]) -> None:
        if not col:
            return
        if table and table != source_name:
            return
        if col in seen:
            return
        seen.add(col)
        out.append(col)

    wells = getattr(spec, "wells", None) or {}
    if isinstance(wells, dict):
        for entries in wells.values():
            if not isinstance(entries, list):
                continue
            for fld in entries:
                col = getattr(fld, "column", None)
                tbl = getattr(fld, "table", None)
                if col is None and isinstance(fld, dict):
                    col = fld.get("column")
                    tbl = fld.get("table")
                _add(col, tbl)
    for f in (spec.filters or []):
        _add(f.column, None)
    return out


def _parse_response(text: str) -> Optional[list]:
    """Best-effort JSON parse. Strip ```json fences if the model
    snuck them in despite the instruction."""
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        return None
    if isinstance(out, dict) and isinstance(out.get("items"), list):
        return out["items"]
    if isinstance(out, list):  # tolerate a bare array
        return out
    return None


def _validate_placements(
    raw_items: list, source: List[DashboardItemView],
) -> List[ItemPlacement]:
    """Convert raw LLM dicts → ItemPlacement, dropping anything that's
    obviously wrong. Then resolve overlaps so the saved layout is
    always non-overlapping."""
    by_id: Dict[int, DashboardItemView] = {it.item_id: it for it in source}
    seen: set[int] = set()
    out: List[ItemPlacement] = []

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        try:
            item_id = int(raw.get("item_id"))
        except (TypeError, ValueError):
            continue
        if item_id in seen or item_id not in by_id:
            continue
        seen.add(item_id)

        original = by_id[item_id]
        # AI Polish does NOT change layout — the user's manual
        # arrangement (drag/drop + Compact-up) is sacred. We always
        # copy grid coords + size_class from the input view, no matter
        # what the LLM proposed. The polish-only contract keeps the
        # button cheap (no surprise re-arrangement) and matches user
        # expectation.
        title_override = raw.get("title_override")
        if isinstance(title_override, str):
            title_override = title_override.strip()[:60] or None
        else:
            title_override = None

        icon = _coerce_icon(raw.get("icon"), original.icon)
        anim_in = _coerce_animation(raw.get("animation_in"), original.animation_in)
        anim_out = _coerce_animation(raw.get("animation_out"), original.animation_out)
        x_label = _coerce_axis_label(raw.get("x_label"), original.x_label, original.chart_type)
        y_label = _coerce_axis_label(raw.get("y_label"), original.y_label, original.chart_type)
        filters = _coerce_filters(raw.get("extra_filters"), original)

        out.append(ItemPlacement(
            item_id=item_id,
            grid_x=original.grid_x,
            grid_y=original.grid_y,
            grid_w=original.grid_w,
            grid_h=original.grid_h,
            size_class=original.size_class,
            title_override=title_override,
            icon=icon,
            animation_in=anim_in,
            animation_out=anim_out,
            x_label=x_label,
            y_label=y_label,
            extra_filters=filters,
        ))

    # Backfill any items the LLM forgot — they keep their existing
    # layout + existing polish (no new icon / animation / filter,
    # just an identity placement so every input item appears in the
    # response). Layout never moves under AI Polish.
    for it in source:
        if it.item_id in seen:
            continue
        out.append(_identity_placement(it))
    return out


def _identity_placement(it: DashboardItemView) -> ItemPlacement:
    """An ItemPlacement that mirrors the input view exactly — used
    when the LLM omits an item or when we need to preserve the
    user's layout under AI Polish."""
    return ItemPlacement(
        item_id=it.item_id,
        grid_x=it.grid_x,
        grid_y=it.grid_y,
        grid_w=it.grid_w,
        grid_h=it.grid_h,
        size_class=it.size_class,
        title_override=it.title_override,
        icon=it.icon,
        animation_in=it.animation_in,
        animation_out=it.animation_out,
        x_label=it.x_label,
        y_label=it.y_label,
        extra_filters=list(it.extra_filters or []),
    )


def _coerce_icon(raw: Any, fallback: Optional[str]) -> Optional[str]:
    """Accept only icons from the curated allow-list. Anything else
    (typos, fabricated names) drops back to the original value so we
    never poison the row."""
    if raw is None:
        return fallback
    if not isinstance(raw, str):
        return fallback
    s = raw.strip().lower().replace("-", "_")
    if not s or s == "null":
        return None
    if s in _VALID_ICONS:
        return s
    return fallback


_AXIS_LABEL_CHART_TYPES = ("bar", "line")
_AXIS_LABEL_MAX_LEN = 30


def _coerce_axis_label(
    raw: Any, fallback: Optional[str], chart_type: str,
) -> Optional[str]:
    """Validate a proposed x_label / y_label.

    * None / "null" / non-string → keep the original value.
    * Empty string → clear the override.
    * Anything else → trim to ``_AXIS_LABEL_MAX_LEN`` chars.
    * Ignored entirely for chart types where axis titles don't render
      (scorecard / pie / table / stat_group). The chart-renderer also
      ignores these slots, but stripping at validation time keeps the
      stored row clean and the response payload honest.
    """
    if chart_type not in _AXIS_LABEL_CHART_TYPES:
        return None
    if raw is None:
        return fallback
    if not isinstance(raw, str):
        return fallback
    s = raw.strip()
    if not s or s.lower() == "null":
        return None
    return s[:_AXIS_LABEL_MAX_LEN]


def _coerce_animation(raw: Any, fallback: Optional[str]) -> Optional[str]:
    if raw is None:
        return fallback
    if not isinstance(raw, str):
        return fallback
    s = raw.strip().lower()
    if not s or s == "null":
        return None
    if s in _VALID_ANIMATIONS:
        return s
    return fallback


def _coerce_filters(
    raw: Any, original: DashboardItemView,
) -> List[BuilderFilter]:
    """Validate proposed filters against the KPI's BuilderSpec when
    available. Filters whose column doesn't exist on the source are
    dropped — defence in depth on top of the spec-compiler check that
    runs at execute time."""
    if raw is None:
        return list(original.extra_filters or [])
    if not isinstance(raw, list):
        return []
    allowed_cols: Optional[set[str]] = None
    if original.builder_spec is not None:
        allowed_cols = set(_filterable_column_names(original.builder_spec))
    out: List[BuilderFilter] = []
    for entry in raw[:_MAX_FILTERS_PER_ITEM]:
        if not isinstance(entry, dict):
            continue
        col = entry.get("column")
        if not isinstance(col, str) or not col.strip():
            continue
        if allowed_cols is not None and col not in allowed_cols:
            # Column the LLM invented or borrowed from another table —
            # skip rather than risk a compile failure at run time.
            continue
        try:
            f = BuilderFilter.model_validate(entry)
        except Exception:
            continue
        out.append(f)
    return out


def _fallback_pack(items: List[DashboardItemView]) -> List[ItemPlacement]:
    """Used when the LLM is unavailable. AI Polish never moves
    cards — even on the fallback path — so this just emits identity
    placements that mirror each input view exactly. The user's
    arrangement (manual or via Compact-up) survives untouched."""
    return [_identity_placement(it) for it in items]


__all__ = [
    "DashboardItemView",
    "ItemPlacement",
    "DecorationResult",
    "decorate_dashboard",
]
