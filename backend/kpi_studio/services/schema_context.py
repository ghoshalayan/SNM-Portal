"""Compact schema text for LLM prompts.

Takes a ``SchemaPayload`` (from the introspector cache) and renders it as
a token-efficient markdown-ish text block. We strip:
  * Most type detail (just the SQL family — INT, VARCHAR, DATE, …)
  * Defaults, autoincrement flags, indexes
  * Column comments (LLMs over-trust them; tables are usually self-evident)

Includes:
  * Primary key marker (``[pk]``)
  * Nullability (``not null`` only, since most cols are nullable)
  * Foreign keys as inline arrows: ``→ Other.col``

Capped at ``max_tables`` and ``max_columns_per_table`` to keep prompts
predictable; over-budget tables get truncated with a note.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from kpi_studio.schemas import ColumnInfo, SchemaPayload, TableInfo


# Strip "(50)", "(38, 2)", "[NULL]" etc. so types are short.
_TYPE_NORM_RE = re.compile(r"\s*\([^)]*\)|\s*\[NULL\]")


def _short_type(t: str) -> str:
    return _TYPE_NORM_RE.sub("", t or "").upper().strip()


def _format_column(c: ColumnInfo) -> str:
    parts: list[str] = [c.name, _short_type(c.type)]
    if c.primary_key:
        parts.append("[pk]")
    if not c.nullable and not c.primary_key:
        parts.append("not null")
    return " ".join(parts)


def _format_table(t: TableInfo, max_cols: int) -> str:
    qualified = f"{t.schema_name}.{t.name}" if t.schema_name else t.name
    lines: list[str] = [f"### {qualified}"]
    if t.comment:
        lines.append(f"_{t.comment.strip()}_")

    cols = t.columns[:max_cols]
    for col in cols:
        line = f"- {_format_column(col)}"
        # Inline FK arrows on the column they constrain.
        for fk in t.foreign_keys:
            if col.name in fk.constrained_columns:
                ref = (
                    f"{fk.referred_schema}.{fk.referred_table}"
                    if fk.referred_schema else fk.referred_table
                )
                ref_cols = ", ".join(fk.referred_columns)
                line += f"  → {ref}({ref_cols})"
                break
        lines.append(line)

    if len(t.columns) > max_cols:
        lines.append(f"- _… {len(t.columns) - max_cols} more columns truncated_")

    return "\n".join(lines)


def build_schema_context(
    payload: SchemaPayload,
    *,
    max_tables: int = 60,
    max_columns_per_table: int = 24,
    table_filter: Optional[Iterable[str]] = None,
) -> str:
    """Render the schema as a compact text block for an LLM system prompt.

    ``table_filter`` (optional) restricts to a specific subset by name —
    useful if the host wants to expose only a curated allow-list of tables
    to the model.
    """
    tables = payload.tables
    if table_filter is not None:
        allow = {n.lower() for n in table_filter}
        tables = [t for t in tables if t.name.lower() in allow]

    truncated_note = ""
    if len(tables) > max_tables:
        truncated_note = (
            f"\n\n_… {len(tables) - max_tables} additional tables not shown. "
            f"Ask the user to narrow the scope if needed._"
        )
        tables = tables[:max_tables]

    blocks = [_format_table(t, max_columns_per_table) for t in tables]
    header = (
        f"Database dialect: **{payload.dialect}**  "
        f"({len(tables)} tables shown)\n"
    )
    return header + "\n\n".join(blocks) + truncated_note
