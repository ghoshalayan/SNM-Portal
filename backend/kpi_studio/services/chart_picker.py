"""Chart-type heuristic.

Inspects a query result and proposes the best-fitting chart type. The
user can override before saving. Intentionally rule-based — no ML — so
the choice is predictable, debuggable, and reproducible across runs.

Returns a ``ChartSuggestion`` containing the chosen type plus a
``config`` dict shaped for the frontend renderer:

  scorecard  → { "value_column": str, "label_column"?: str }
  bar        → { "category_column": str, "value_column": str }
  line       → { "x_column": str, "y_column": str }
  pie        → { "category_column": str, "value_column": str }
  table      → { "columns": [str, ...] }
  stat_group → { "value_columns": [str, ...] }
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Sequence

# Heuristic thresholds — exposed as module constants so tests / UI can read them.
PIE_BAR_MAX_CATEGORIES = 6
LINE_MIN_POINTS = 3

# A column is considered "datelike" if every non-null value parses as
# ISO date/datetime, or if its name matches a common date-ish suffix.
_DATE_COLUMN_NAMES_RE = re.compile(
    r"(date|day|month|year|on|_at|time|timestamp|created|updated|posted)$",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T\s].*)?$")


CHART_TYPES = ("scorecard", "stat_group", "bar", "line", "pie", "table")


@dataclass
class ChartSuggestion:
    type: str
    """One of CHART_TYPES."""

    config: dict[str, Any]
    """Renderer-specific payload — see module docstring."""

    reason: str = ""
    """Human-readable explanation of *why* this type was chosen."""

    alternates: List[str] = field(default_factory=list)
    """Other types the user could reasonably switch to."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suggest_chart(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> ChartSuggestion:
    """Pick a chart type from a query result.

    Decisions, in order:
      1. Empty → table (degenerate fallback).
      2. 1 row × 1 number → scorecard.
      3. 1 row × N numbers → stat_group.
      4. Date-ish column + numeric column (>= LINE_MIN_POINTS rows) → line.
      5. Single categorical + numeric (<= PIE_BAR_MAX_CATEGORIES) → bar.
         (Pie offered as alternate when row count is tiny.)
      6. Otherwise → table.
    """
    cols = list(columns)
    n_rows = len(rows)

    if not cols or n_rows == 0:
        return ChartSuggestion(
            type="table",
            config={"columns": cols},
            reason="Empty result.",
        )

    # Profile each column.
    profiles = [_profile_column(name, [row[i] for row in rows]) for i, name in enumerate(cols)]
    numeric_cols = [p for p in profiles if p.kind == "numeric"]
    date_cols = [p for p in profiles if p.kind == "date"]
    string_cols = [p for p in profiles if p.kind == "string"]

    # ---- Single-row results -------------------------------------------
    if n_rows == 1:
        if len(cols) == 1 and numeric_cols:
            return ChartSuggestion(
                type="scorecard",
                config={"value_column": numeric_cols[0].name},
                reason="Single numeric value.",
                alternates=["table"],
            )
        if numeric_cols:
            return ChartSuggestion(
                type="stat_group",
                config={"value_columns": [p.name for p in numeric_cols]},
                reason="Single row with multiple numeric columns.",
                alternates=["table"],
            )
        return ChartSuggestion(
            type="table",
            config={"columns": cols},
            reason="Single row, no numeric columns.",
        )

    # ---- Time series --------------------------------------------------
    if date_cols and numeric_cols and n_rows >= LINE_MIN_POINTS:
        return ChartSuggestion(
            type="line",
            config={
                "x_column": date_cols[0].name,
                "y_column": numeric_cols[0].name,
            },
            reason=f"Date column '{date_cols[0].name}' + numeric '{numeric_cols[0].name}'.",
            alternates=["bar", "table"],
        )

    # ---- Categorical breakdown ----------------------------------------
    if string_cols and numeric_cols and len(string_cols) == 1:
        cat = string_cols[0]
        if cat.distinct_count <= PIE_BAR_MAX_CATEGORIES and n_rows <= PIE_BAR_MAX_CATEGORIES:
            return ChartSuggestion(
                type="bar",
                config={
                    "category_column": cat.name,
                    "value_column": numeric_cols[0].name,
                },
                reason=f"One categorical column '{cat.name}' ({cat.distinct_count} categories) + numeric.",
                alternates=["pie", "table"],
            )
        return ChartSuggestion(
            type="bar",
            config={
                "category_column": cat.name,
                "value_column": numeric_cols[0].name,
            },
            reason=f"One categorical column + numeric across {n_rows} rows.",
            alternates=["table"],
        )

    # ---- Default fallback ---------------------------------------------
    return ChartSuggestion(
        type="table",
        config={"columns": cols},
        reason="No clear chart shape — defaulting to table.",
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

@dataclass
class _ColumnProfile:
    name: str
    kind: str            # "numeric" | "date" | "string" | "bool" | "empty"
    distinct_count: int


def _profile_column(name: str, values: Sequence[Any]) -> _ColumnProfile:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return _ColumnProfile(name=name, kind="empty", distinct_count=0)

    distinct = len({_hashable(v) for v in non_null})

    if all(isinstance(v, bool) for v in non_null):
        return _ColumnProfile(name=name, kind="bool", distinct_count=distinct)

    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
        return _ColumnProfile(name=name, kind="numeric", distinct_count=distinct)

    # String with a date-ish *name* and ISO-looking values is treated as date.
    if all(isinstance(v, str) for v in non_null):
        looks_like_date = (
            _DATE_COLUMN_NAMES_RE.search(name) is not None
            and all(_ISO_DATE_RE.match(v) for v in non_null)
        )
        if looks_like_date:
            return _ColumnProfile(name=name, kind="date", distinct_count=distinct)
        return _ColumnProfile(name=name, kind="string", distinct_count=distinct)

    return _ColumnProfile(name=name, kind="string", distinct_count=distinct)


def _hashable(v: Any) -> Any:
    """Make `v` usable in a set; collapses unhashable types to their repr."""
    try:
        hash(v)
        return v
    except TypeError:
        return repr(v)
