"""Tool definitions + handlers for the agentic NL→SQL loop (Phase A7).

Five tools the model can call:
  * ``list_tables``           — names + comments + column counts
  * ``describe_table``        — full column / FK / PK info
  * ``peek_distinct_values``  — top-N distinct values of a column (live read)
  * ``validate_sql``          — runs the safety validator without executing
  * ``propose_sql``           — terminator; final answer

Schema lookups (``list_tables``, ``describe_table``) read from the cached
``KpiSchemaSnapshot``, not the live DB. Only ``peek_distinct_values``
hits the target engine — and even that goes through the safety validator
+ executor (read-only, statement timeout, row cap).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from kpi_studio.providers.llm.base import LlmTool
from kpi_studio.schemas import SchemaPayload, TableInfo
from kpi_studio.services.executor import (
    QueryExecutionError, execute_safe_query,
)
from kpi_studio.services.sql_safety import (
    SqlSafetyError, validate_select_query,
)


# Plain-identifier regex — allows letters, digits, underscores. We refuse
# anything else for table/column names so the agent can't smuggle SQL
# fragments through ``peek_distinct_values``.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# ---------------------------------------------------------------------------
# Tool descriptors — JSON-Schema parameter shapes the LLM sees.
# ---------------------------------------------------------------------------

TOOL_LIST_TABLES = LlmTool(
    name="list_tables",
    description=(
        "Return the catalog of tables visible to the analytics tool. "
        "Use this first to understand what data exists. Output is a list "
        "of {schema, name, comment, column_count}."
    ),
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)

TOOL_DESCRIBE_TABLE = LlmTool(
    name="describe_table",
    description=(
        "Return columns, primary key, and foreign keys for one table. "
        "Call this after list_tables to learn the shape of a specific "
        "table. Returns column name, type, nullable, primary_key plus "
        "any FK references."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name":   {"type": "string", "description": "Table name (no schema prefix)"},
            "schema": {"type": "string", "description": "Optional schema name"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
)

TOOL_PEEK_DISTINCT_VALUES = LlmTool(
    name="peek_distinct_values",
    description=(
        "Return up to N distinct values from one column of one table. "
        "Use this to disambiguate categorical columns (e.g. status, "
        "region, type) before writing the final SQL. Cheap (TOP N "
        "DISTINCT, capped at 25). Reads live data through a read-only "
        "connection."
    ),
    parameters={
        "type": "object",
        "properties": {
            "table":  {"type": "string"},
            "column": {"type": "string"},
            "schema": {"type": "string"},
            "limit":  {"type": "integer", "minimum": 1, "maximum": 25, "default": 10},
        },
        "required": ["table", "column"],
        "additionalProperties": False,
    },
)

TOOL_VALIDATE_SQL = LlmTool(
    name="validate_sql",
    description=(
        "Check a SELECT statement against the safety validator without "
        "executing it. Use this before propose_sql to catch issues like "
        "DDL/DML, system tables, or disallowed parameter markers."
    ),
    parameters={
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
        "additionalProperties": False,
    },
)

TOOL_PROPOSE_SQL = LlmTool(
    name="propose_sql",
    description=(
        "Submit the final SQL answer + a 1-3 sentence explanation. This "
        "ends the agent loop. Always call this once you have a query "
        "you're confident will answer the user's question. If the schema "
        "doesn't support the question, call propose_sql with sql='' and "
        "an explanation of why."
    ),
    parameters={
        "type": "object",
        "properties": {
            "sql":         {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": ["sql", "explanation"],
        "additionalProperties": False,
    },
)

ALL_TOOLS: list[LlmTool] = [
    TOOL_LIST_TABLES,
    TOOL_DESCRIBE_TABLE,
    TOOL_PEEK_DISTINCT_VALUES,
    TOOL_VALIDATE_SQL,
    TOOL_PROPOSE_SQL,
]


# ---------------------------------------------------------------------------
# Handler context + dispatch
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    """Bundle of dependencies the tool handlers need.

    Carrying these as a context object (rather than method args) keeps
    the dispatch table small and makes it easy to swap engines for tests.
    """
    schema: SchemaPayload
    target_engine: Engine
    db: Session
    user_id: Optional[int]
    company_id: Optional[int]
    safe_dialect: str
    """``tsql`` for SQL Server, ``sqlite`` etc. for tests."""


class ToolError(Exception):
    """Raised when a tool handler refuses to run (bad args, banned ident)."""


def dispatch(name: str, args: dict, ctx: ToolContext) -> Any:
    """Run one tool by name. Returns a JSON-safe dict; raises ``ToolError``
    on validation failure (orchestrator surfaces the message back to the
    model so it can correct itself)."""
    if name == "list_tables":
        return _list_tables(ctx)
    if name == "describe_table":
        return _describe_table(args, ctx)
    if name == "peek_distinct_values":
        return _peek_distinct_values(args, ctx)
    if name == "validate_sql":
        return _validate_sql(args)
    # ``propose_sql`` is handled by the orchestrator — terminator, not a
    # data-fetching tool. If the model dispatches it here it's a bug
    # upstream; surface it as such.
    raise ToolError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _list_tables(ctx: ToolContext) -> dict:
    return {
        "tables": [
            {
                "schema": t.schema_name,
                "name": t.name,
                "comment": t.comment,
                "column_count": len(t.columns),
            }
            for t in ctx.schema.tables
        ],
    }


def _find_table(name: str, schema: Optional[str], payload: SchemaPayload) -> Optional[TableInfo]:
    nlow = name.lower()
    for t in payload.tables:
        if t.name.lower() != nlow:
            continue
        if schema and (t.schema_name or "").lower() != schema.lower():
            continue
        return t
    return None


def _describe_table(args: dict, ctx: ToolContext) -> dict:
    name = (args.get("name") or "").strip()
    schema = (args.get("schema") or "").strip() or None
    if not name:
        raise ToolError("describe_table: 'name' is required")

    table = _find_table(name, schema, ctx.schema)
    if table is None:
        raise ToolError(
            f"describe_table: table '{schema + '.' if schema else ''}{name}' "
            f"not found in the cached schema snapshot."
        )

    return {
        "schema": table.schema_name,
        "name": table.name,
        "comment": table.comment,
        "primary_key": list(table.primary_key),
        "columns": [
            {
                "name": c.name,
                "type": c.type,
                "nullable": c.nullable,
                "primary_key": c.primary_key,
            }
            for c in table.columns
        ],
        "foreign_keys": [
            {
                "constrained_columns": fk.constrained_columns,
                "referred_schema": fk.referred_schema,
                "referred_table": fk.referred_table,
                "referred_columns": fk.referred_columns,
            }
            for fk in table.foreign_keys
        ],
    }


def _peek_distinct_values(args: dict, ctx: ToolContext) -> dict:
    """Build a tiny ``SELECT DISTINCT TOP N <column> FROM <table>`` query,
    run it through the same safety validator + executor everything else
    uses, and return the result as a JSON-safe list of values.
    """
    table = (args.get("table") or "").strip()
    column = (args.get("column") or "").strip()
    schema = (args.get("schema") or "").strip() or None
    limit = int(args.get("limit") or 10)
    limit = max(1, min(25, limit))

    if not _IDENT_RE.match(table):
        raise ToolError(f"peek_distinct_values: unsafe table identifier {table!r}")
    if not _IDENT_RE.match(column):
        raise ToolError(f"peek_distinct_values: unsafe column identifier {column!r}")
    if schema and not _IDENT_RE.match(schema):
        raise ToolError(f"peek_distinct_values: unsafe schema identifier {schema!r}")

    # Cross-check against the cached schema so the agent can't probe
    # tables/columns that were excluded from the snapshot (e.g. system
    # schemas) even with a syntactically-valid identifier.
    table_info = _find_table(table, schema, ctx.schema)
    if table_info is None:
        raise ToolError(
            f"peek_distinct_values: table {table!r} not found in snapshot."
        )
    if not any(c.name.lower() == column.lower() for c in table_info.columns):
        raise ToolError(
            f"peek_distinct_values: column {column!r} not on table {table!r}."
        )

    qualified = (
        f"{schema}.{table}" if schema and ctx.safe_dialect == "tsql" else table
    )
    if ctx.safe_dialect == "tsql":
        sql = f"SELECT DISTINCT TOP {limit} {column} FROM {qualified}"
    else:
        sql = f"SELECT DISTINCT {column} FROM {qualified} LIMIT {limit}"

    try:
        result = execute_safe_query(
            ctx.target_engine,
            ctx.db,
            sql=sql,
            source="nl_agent",
            user_id=ctx.user_id,
            company_id=ctx.company_id,
        )
    except SqlSafetyError as exc:
        # Almost impossible — we built the SQL ourselves — but bubble cleanly.
        raise ToolError(f"peek_distinct_values: validator rejected: {exc}")
    except QueryExecutionError as exc:
        raise ToolError(f"peek_distinct_values: execution failed: {exc}")

    return {
        "table": table,
        "column": column,
        "values": [row[0] for row in result.rows],
        "row_count": result.row_count,
    }


def _validate_sql(args: dict) -> dict:
    sql = (args.get("sql") or "").strip()
    if not sql:
        return {"ok": False, "message": "Empty SQL.", "findings": []}
    try:
        safe = validate_select_query(sql)
    except SqlSafetyError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "findings": list(getattr(exc, "findings", []) or []),
        }
    return {
        "ok": True,
        "rewritten_sql": safe.rewritten,
        "row_cap": safe.row_cap,
        "notes": list(safe.notes),
    }
