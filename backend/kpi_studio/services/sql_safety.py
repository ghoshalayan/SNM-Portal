"""SQL safety layer.

The keystone of KPI Studio's defence-in-depth: even with a read-only DB
login (recommended via ``KPI_DSN``) the parser-level guard rejects whole
classes of bad inputs *before* anything reaches the engine.

Rules:
  * Exactly one statement (no batched ``;`` payloads).
  * Statement must be a ``SELECT`` (or a ``WITH … SELECT``).
  * No DDL / DML / DCL / TCL.
  * No system schemas (``sys``, ``INFORMATION_SCHEMA``, ``master``,
    ``msdb``, ``model``, ``tempdb``).
  * No SQL Server "danger" calls: ``xp_*``, ``sp_executesql``,
    ``OPENROWSET``, ``OPENQUERY``, ``OPENDATASOURCE``, ``BULK``.
  * Reject parameter markers (``?``, ``:name``, ``@var``) — Phase A1
    doesn't bind parameters, so anything looking like one is suspicious.
  * Inject a ``LIMIT`` (or SQL Server ``TOP``) if the user didn't write
    one. Hard cap configurable per call.

Returns a ``SafeQuery`` containing the rewritten SQL ready for the
executor, plus structured findings the API can surface to the user.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import sqlglot
from sqlglot import exp


# Named placeholders the validator allows in user-authored SQL. The
# executor binds these to wall-clock dates derived from the time-period
# selector (services/time_periods.py). Any other parameter marker is
# still rejected — the allow-list is purposefully tiny.
ALLOWED_NAMED_PARAMS = frozenset((
    "start_date", "end_date",
    # Phase I — auto-bound by the API layer on every run so a single
    # KPI can serve every caller with their own data slice.
    "company_id", "user_id",
))


SQL_SERVER_SYSTEM_SCHEMAS = frozenset(
    s.lower() for s in (
        "sys", "information_schema", "master", "msdb", "model", "tempdb",
    )
)

# Function/procedure names that are categorically banned. Matched
# case-insensitively against the bare name (no schema).
BANNED_FUNCTIONS = frozenset(
    s.lower() for s in (
        "openrowset", "openquery", "opendatasource", "openjson",
        "bulk_insert", "sp_executesql", "sp_addextendedproc",
    )
)

# Bare-token patterns that indicate an attempt to escape via raw text.
# Checked against the original string (sqlglot will sometimes parse these
# but we'd rather refuse them outright).
DANGER_TOKENS_RE = re.compile(
    r"\b(xp_\w+|sp_executesql|openrowset|openquery|opendatasource|bulk\s+insert)\b",
    re.IGNORECASE,
)

# SQL Server identifier delimiter for safety in TOP injection.
_TOP_INJECT_RE = re.compile(r"^\s*select\b", re.IGNORECASE)


class SqlSafetyError(ValueError):
    """Raised when a query is rejected by the safety layer."""

    def __init__(self, message: str, *, findings: list[str] | None = None) -> None:
        super().__init__(message)
        self.findings = findings or [message]


@dataclass
class SafeQuery:
    """Result of a successful safety pass."""

    original: str
    rewritten: str
    """SQL ready to hand to the executor — may include an injected LIMIT/TOP."""

    row_cap: int
    """The cap that was applied (either user's existing LIMIT or the injected one)."""

    notes: List[str] = field(default_factory=list)
    """Human-readable notes (e.g. "Injected TOP 50000")."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_select_query(
    sql: str,
    *,
    row_cap: int = 50_000,
    dialect: str = "tsql",
) -> SafeQuery:
    """Validate ``sql`` and return a rewritten safe-to-execute version.

    Raises ``SqlSafetyError`` with a useful message + findings list if the
    query violates any rule.
    """
    raw = (sql or "").strip().rstrip(";").strip()
    if not raw:
        raise SqlSafetyError("Empty query.")

    # --- 1. Bare-token sanity check on the raw text. --------------------
    danger = DANGER_TOKENS_RE.findall(raw)
    if danger:
        raise SqlSafetyError(
            f"Query contains disallowed tokens: {', '.join(sorted(set(danger)))}",
            findings=[f"Disallowed token: {tok}" for tok in danger],
        )

    # --- 2. Reject positional parameter markers ('?'). ------------------
    # Positional ``?`` placeholders are unbindable from our API surface
    # (we don't know how many to provide); always rejected. Named ``:foo``
    # placeholders are checked against ALLOWED_NAMED_PARAMS in step 6.
    if "?" in raw:
        raise SqlSafetyError("Positional parameter markers (?) are not supported.")

    # --- 3. Parse via sqlglot (T-SQL dialect by default for SNM). --------
    try:
        parsed_list = sqlglot.parse(raw, dialect=dialect)
    except Exception as exc:
        raise SqlSafetyError(f"SQL parse error: {exc}") from exc

    # Filter out None entries (sqlglot may return them for trailing tokens).
    statements = [s for s in parsed_list if s is not None]
    if not statements:
        raise SqlSafetyError("No parseable statement found.")
    if len(statements) > 1:
        raise SqlSafetyError(
            "Only one statement allowed per query.",
            findings=[f"Got {len(statements)} statements; expected 1."],
        )
    tree = statements[0]

    # --- 4. Top-level must be a SELECT (or a WITH ending in SELECT). ----
    top = tree
    # Unwrap CTE: a WITH … SELECT is a Select with a `with` arg in sqlglot.
    if not isinstance(top, exp.Select):
        # `Subquery` wrapper, `Union`, etc. — disallow non-SELECT roots
        # except for unions of SELECTs.
        if isinstance(top, exp.Union):
            pass  # allowed
        else:
            raise SqlSafetyError(
                f"Only SELECT (or UNION of SELECTs) is allowed; got {type(top).__name__.upper()}.",
            )

    # --- 5. AST scan for forbidden node types. --------------------------
    forbidden_node_types = (
        exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Alter,
        exp.Create, exp.Drop, exp.TruncateTable, exp.Use, exp.Set,
        exp.Command,  # generic catch-all sqlglot uses for unknown verbs (EXEC, GRANT, …)
    )
    bad = list(tree.find_all(*forbidden_node_types))
    if bad:
        raise SqlSafetyError(
            "Query contains a non-SELECT operation.",
            findings=[f"Disallowed node: {type(n).__name__}" for n in bad],
        )

    # --- 6. Allow only named placeholders from ALLOWED_NAMED_PARAMS. ----
    # ``:start_date`` / ``:end_date`` are bound by the executor; everything
    # else is a footgun (and a SQL injection vector if mis-bound).
    bad_params: list[str] = []
    for node in tree.find_all(exp.Parameter, exp.Placeholder):
        # ``Parameter.this`` is the inner name (Identifier or Literal node).
        # ``Placeholder.this`` follows the same shape. Best-effort extract.
        name_node = getattr(node, "this", None)
        if name_node is None:
            bad_params.append(node.sql() or "<unnamed>")
            continue
        name = (
            getattr(name_node, "name", None)
            or getattr(name_node, "this", None)
            or str(name_node)
        ).strip().lstrip(":@").lower()
        if name not in ALLOWED_NAMED_PARAMS:
            bad_params.append(f":{name}" if name else "<unnamed>")
    if bad_params:
        raise SqlSafetyError(
            f"Disallowed parameter markers: {', '.join(sorted(set(bad_params)))}. "
            f"Only {sorted(ALLOWED_NAMED_PARAMS)} are accepted.",
            findings=[f"Disallowed marker: {p}" for p in sorted(set(bad_params))],
        )

    # --- 7. Reject system-schema references. ----------------------------
    bad_schemas = []
    for table in tree.find_all(exp.Table):
        # sqlglot stores schema in `db` for SQL Server; some dialects use
        # `catalog`. Check both.
        for attr in ("db", "catalog"):
            ref = table.args.get(attr)
            if ref is None:
                continue
            name = (ref.name if hasattr(ref, "name") else str(ref)).strip("[]\"`")
            if name and name.lower() in SQL_SERVER_SYSTEM_SCHEMAS:
                bad_schemas.append(f"{name}.{table.name}")
    if bad_schemas:
        raise SqlSafetyError(
            "Query references a system schema.",
            findings=[f"System table: {ref}" for ref in bad_schemas],
        )

    # Also check that the table name itself isn't a system view (e.g.
    # bare ``SELECT * FROM sysobjects``).
    for table in tree.find_all(exp.Table):
        bare = table.name.strip("[]\"`").lower()
        if bare.startswith(("sys", "msys")) and len(bare) > 3:
            raise SqlSafetyError(
                f"Query references a system table: {table.name}",
                findings=[f"System table: {table.name}"],
            )

    # --- 8. Reject banned function calls. -------------------------------
    bad_funcs = []
    for func in tree.find_all(exp.Func):
        name = (func.sql_name() if hasattr(func, "sql_name") else "").lower()
        if not name and hasattr(func, "name"):
            name = (func.name or "").lower()
        if name in BANNED_FUNCTIONS:
            bad_funcs.append(name)
    # `Anonymous` covers parser-unknown functions like xp_cmdshell.
    for anon in tree.find_all(exp.Anonymous):
        n = (anon.this or "").lower()
        if n in BANNED_FUNCTIONS or n.startswith("xp_") or n.startswith("sp_"):
            bad_funcs.append(n)
    if bad_funcs:
        raise SqlSafetyError(
            f"Query calls a banned function: {', '.join(sorted(set(bad_funcs)))}",
            findings=[f"Banned function: {n}" for n in sorted(set(bad_funcs))],
        )

    # --- 9. Inject TOP if the user didn't write one. --------------------
    rewritten, applied_cap, notes = _inject_row_cap(tree, row_cap, dialect)

    return SafeQuery(
        original=raw,
        rewritten=rewritten,
        row_cap=applied_cap,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _inject_row_cap(
    tree: exp.Expression,
    row_cap: int,
    dialect: str,
) -> tuple[str, int, list[str]]:
    """Ensure the query is bounded by ``row_cap``.

    For T-SQL we use ``SELECT TOP n ...``. For other dialects we use
    ``LIMIT n``. If the user already wrote one and it's <= ``row_cap``,
    we leave it alone; if it's higher we lower it to the cap.
    """
    notes: list[str] = []

    if dialect == "tsql":
        # SQL Server: TOP is part of the SELECT node's "limit" arg in sqlglot.
        if isinstance(tree, exp.Select):
            existing = tree.args.get("limit")
            if existing is None:
                tree.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
                notes.append(f"Injected TOP {row_cap}")
                applied = row_cap
            else:
                # User wrote TOP/LIMIT — clamp.
                applied = _coerce_int(existing, fallback=row_cap)
                if applied > row_cap:
                    tree.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
                    notes.append(f"Lowered TOP from {applied} to {row_cap}")
                    applied = row_cap
        else:
            # UNION etc — wrap in a SELECT * with TOP.
            wrapper = exp.Select(
                expressions=[exp.Star()],
                **{"from": exp.From(this=exp.Subquery(this=tree, alias="kpi_q"))},
            )
            wrapper.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
            tree = wrapper
            notes.append(f"Wrapped UNION in TOP {row_cap}")
            applied = row_cap

        rewritten = tree.sql(dialect=dialect)
        return rewritten, applied, notes

    # Generic LIMIT path (sqlite, postgres, etc.)
    if isinstance(tree, exp.Select):
        existing = tree.args.get("limit")
        if existing is None:
            tree.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
            notes.append(f"Injected LIMIT {row_cap}")
            applied = row_cap
        else:
            applied = _coerce_int(existing, fallback=row_cap)
            if applied > row_cap:
                tree.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
                notes.append(f"Lowered LIMIT from {applied} to {row_cap}")
                applied = row_cap
    else:
        wrapper = exp.Select(expressions=[exp.Star()]).from_(exp.Subquery(this=tree, alias="kpi_q"))
        wrapper.set("limit", exp.Limit(expression=exp.Literal.number(row_cap)))
        tree = wrapper
        notes.append(f"Wrapped UNION in LIMIT {row_cap}")
        applied = row_cap

    return tree.sql(dialect=dialect), applied, notes


def _coerce_int(limit_node: exp.Expression, *, fallback: int) -> int:
    """Best-effort extract of the integer value from a Limit node."""
    try:
        inner = getattr(limit_node, "expression", None) or limit_node
        if isinstance(inner, exp.Literal):
            return int(inner.this)
        text = inner.sql()
        return int(re.search(r"-?\d+", text).group(0))  # type: ignore[union-attr]
    except Exception:
        return fallback
