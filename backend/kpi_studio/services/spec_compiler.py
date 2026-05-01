"""BuilderSpec → SQL + chart_config compiler (Phase C — Smart Builder).

Power BI's authoring model is "drag fields into wells, get a chart."
Each visual type advertises a fixed set of named wells (Axis, Values,
Legend, etc.); the user drops columns + picks aggregations + filters,
and Power BI compiles all of that into a query that drives the visual.

This module is the equivalent for KPI Studio. It takes a ``BuilderSpec``
and emits:
  * a deterministic, executor-safe SQL string in the host dialect
  * a matching ``ChartConfig`` payload that maps result columns onto the
    renderer's expected ``category_column`` / ``value_column`` / etc. keys

Design notes
------------
* **Identifier quoting** — every column / table / schema name is checked
  against a strict identifier regex *and* wrapped in T-SQL square
  brackets. Anything outside ``[A-Za-z_][A-Za-z0-9_]*`` is rejected at
  compile time. The safety validator (``sql_safety.validate_select_query``)
  runs over the compiled SQL as a backstop.
* **Filter values** are inlined as quoted literals rather than bind
  params. Reasons:
    - The executor only binds ``:start_date`` / ``:end_date`` from the
      runtime period; persisting per-KPI bind params would need a new
      column on ``KpiVersion``.
    - Filter values come from a UI dropdown / typed input where types
      are known up-front; the literal helper handles every Python value
      we accept (str, int, float, bool, None, datetime, list).
* **Time-binding** — when ``spec.time_column`` is set the compiler
  injects ``[time_column] BETWEEN :start_date AND :end_date`` so the
  dashboard's period selector binds straight onto the KPI, identical
  to how raw-SQL KPIs use the placeholders.
* The compiler is the only place dialect-specific syntax lives; if a
  second dialect ever lands, we branch here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime
from typing import Any, List, Optional, Sequence

from kpi_studio.schemas import (
    AggregateFilter, BuilderField, BuilderFilter, BuilderSpec,
    ChartConfig, CompiledSpec,
)

# Identifier pattern — column / table / schema names must match this.
# Deliberately strict: alphanum + underscore, must not start with digit.
# This is broader than ANSI but enough for typical app schemas.
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Per-chart-type well definitions — what wells the visual accepts and
# how many fields each accepts. ``required`` is enforced; ``optional``
# wells may be empty. Anything outside these names triggers a compile
# error so a malformed spec from a buggy frontend can't slip through.
_WELL_RULES: dict[str, dict[str, Any]] = {
    "scorecard": {
        "required": {"value": (1, 1)},
        "optional": {"label": (0, 1)},
    },
    "stat_group": {
        "required": {"values": (1, 12)},
        "optional": {},
    },
    "bar": {
        "required": {"axis": (1, 1), "values": (1, 1)},
        "optional": {"legend": (0, 1)},
    },
    "pie": {
        "required": {"axis": (1, 1), "values": (1, 1)},
        "optional": {},
    },
    "line": {
        "required": {"axis": (1, 1), "values": (1, 1)},
        "optional": {"legend": (0, 1)},
    },
    "table": {
        "required": {"columns": (1, 50)},
        "optional": {},
    },
}


class SpecCompileError(ValueError):
    """Raised on any structural problem in a BuilderSpec — bad
    identifier, missing well, illegal aggregation, etc. Message is
    user-facing; the API layer surfaces it as a 400."""


@dataclass
class _SqlBuilder:
    """Tiny accumulator used while threading clauses together."""
    select: List[str]
    from_clause: str
    where: List[str]
    group_by: List[str]
    order_by: List[str]
    # Phase G.2 — HAVING predicates (aggregate-value filters). Same
    # AND-joined model as ``where`` but rendered after GROUP BY.
    having: List[str] = dc_field(default_factory=list)
    # Phase F — joins added by ``_ensure_joined`` as fields from related
    # tables are referenced. Each entry is a fully-rendered LEFT JOIN
    # clause, e.g. ``LEFT JOIN [customers] ON [enquiries].[customer_id] = [customers].[id]``.
    joins: List[str] = dc_field(default_factory=list)
    # Set of (schema, table) tuples already in the FROM/JOIN chain so
    # we don't double-join the same table.
    joined_tables: set = dc_field(default_factory=set)
    # Phase G — when derived columns exist, the source is wrapped in a
    # CTE; this is the rendered ``WITH __src AS (...)`` clause that
    # prefixes the final SELECT.
    cte_prefix: str = ""
    top_n: Optional[int] = None

    def render(self) -> str:
        top = f"TOP {int(self.top_n)} " if self.top_n else ""
        parts: List[str] = []
        if self.cte_prefix:
            parts.append(self.cte_prefix)
        parts.append(f"SELECT {top}{', '.join(self.select)}")
        parts.append(f"FROM {self.from_clause}")
        if self.joins:
            parts.extend(self.joins)
        if self.where:
            parts.append("WHERE " + " AND ".join(self.where))
        if self.group_by:
            parts.append("GROUP BY " + ", ".join(self.group_by))
        if self.having:
            parts.append("HAVING " + " AND ".join(self.having))
        if self.order_by:
            parts.append("ORDER BY " + ", ".join(self.order_by))
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_spec(
    spec: BuilderSpec,
    *,
    relationships: Optional[Sequence[Any]] = None,
) -> CompiledSpec:
    """Validate + compile a ``BuilderSpec`` into a ready-to-execute
    SQL string and matching chart config.

    ``relationships`` is the relationship graph used to auto-emit
    LEFT JOINs when a BuilderField references a column from a table
    other than the source. Each item must expose ``from_schema``,
    ``from_table``, ``from_column``, ``to_schema``, ``to_table``,
    ``to_column``, and ``is_active`` attributes (the live
    ``KpiTableRelationship`` ORM rows from
    ``relationship_service.list_relationships``).
    """
    notes: list[str] = []
    _validate_wells(spec)

    source_schema = spec.source.schema_name
    source_table = spec.source.name

    # Phase G — when derived columns are present, wrap the source in a
    # CTE so each expression evaluates once per row and downstream
    # references resolve via the alias. Without derived columns,
    # FROM/qualification stay exactly as Phase F left them.
    derived = list(spec.derived_columns or [])
    source_alias = "__src" if derived else None
    derived_aliases: set = set()

    builder = _SqlBuilder(
        select=[],
        from_clause=(_quote_ident(source_alias) if source_alias
                     else _quote_table(source_schema, source_table)),
        where=[],
        group_by=[],
        order_by=[],
        top_n=spec.top_n,
    )
    # The "source" sits on the joined-tables map under both its
    # physical (schema, table) and alias. ``_ensure_joined`` checks
    # before adding a JOIN; we want the source to count as already-
    # joined either way it's referenced.
    builder.joined_tables.add((source_schema or "", source_table))
    if source_alias:
        builder.joined_tables.add(("", source_alias))
        # Render the CTE prefix once. Source-column expressions are
        # NOT qualified inside the CTE (it's a single-table SELECT *),
        # so they read like the user typed them.
        derived_select_parts = ["*"]
        for d in derived:
            _ident(d.alias)
            if d.alias in derived_aliases:
                raise SpecCompileError(f"Duplicate derived column alias: {d.alias!r}")
            derived_aliases.add(d.alias)
            expr = (d.expression or "").strip()
            if not expr:
                raise SpecCompileError(f"Derived column {d.alias!r} has empty expression.")
            # Quick guard against multi-statement injection. The full
            # downstream sql_safety pass catches DDL / DML / multiple
            # statements; this is a friendlier early error.
            if ";" in expr:
                raise SpecCompileError(
                    f"Derived column {d.alias!r}: semicolons are not allowed in expressions.",
                )
            derived_select_parts.append(f"({expr}) AS {_quote_ident(d.alias)}")
        builder.cte_prefix = (
            f"WITH {_quote_ident(source_alias)} AS (\n"
            f"  SELECT {', '.join(derived_select_parts)}\n"
            f"  FROM {_quote_table(source_schema, source_table)}\n"
            f")"
        )

    rels = list(relationships or [])

    # Bind so emitter helpers can reach them without a global.
    ctx = _CompileCtx(
        source_schema=source_schema,
        source_table=source_table,
        source_alias=source_alias,
        derived_aliases=derived_aliases,
        relationships=rels,
        notes=notes,
    )

    # Time binding — same placeholders raw-SQL KPIs use. Always emit
    # both bounds so the executor's wide-window fallback covers the
    # "no period selected" case without erroring on missing binds.
    if spec.time_column:
        _ident(spec.time_column)  # validate
        time_col_qual = (
            _qual_col_str(None, source_alias, spec.time_column) if source_alias
            else _qual_col_str(source_schema, source_table, spec.time_column)
        )
        builder.where.append(
            f"{time_col_qual} BETWEEN :start_date AND :end_date"
        )

    # Filters — translated one-by-one. Literal values are escaped via
    # ``_render_filter``; the safety validator is the second line of
    # defence after this helper.
    for f in spec.filters:
        builder.where.append(_render_filter(
            f,
            source_schema=source_schema,
            source_table=source_table,
            source_alias=source_alias,
        ))

    # Phase G.2 — aggregate filters (HAVING). The aggregate expression
    # is built the same way ``_render_agg_expr`` builds the SELECT-side
    # one, so HAVING references match exactly (some engines resolve by
    # alias, others by expression — emitting the expression is portable).
    for af in spec.aggregate_filters or []:
        builder.having.append(_render_aggregate_filter(
            af, builder=builder, ctx=ctx,
        ))

    chart_config = _emit_for_chart_type(spec, builder, ctx)

    sql = builder.render()
    # Trailing semicolon helps some clients but isn't required; omit
    # to keep round-trips identical to raw-SQL KPIs (which we don't
    # auto-add semicolons to either).
    return CompiledSpec(sql=sql, chart_config=chart_config, notes=notes)


@dataclass
class _CompileCtx:
    source_schema: Optional[str]
    source_table: str
    relationships: list
    notes: list
    # Phase G — when set, source-table column references qualify via
    # the CTE alias instead of the physical [schema].[table]. ``None``
    # = no derived columns, behave as Phase F.
    source_alias: Optional[str] = None
    # Aliases of derived columns. Used for two things: (1) reject a
    # BuilderField that references a derived alias *and* sets a
    # ``table`` to something other than the source; (2) prevent a
    # join lookup when the field's column matches a derived alias.
    derived_aliases: set = dc_field(default_factory=set)


# ---------------------------------------------------------------------------
# Per-chart-type emitters
#
# Each one mutates ``builder`` (SELECT / GROUP BY / ORDER BY) and
# returns the matching ``ChartConfig`` for the renderer. Field column
# references go through ``_qual_col`` which auto-emits a LEFT JOIN
# when the field's table is different from the source.
# ---------------------------------------------------------------------------

def _emit_for_chart_type(
    spec: BuilderSpec, builder: _SqlBuilder, ctx: _CompileCtx,
) -> ChartConfig:
    chart = spec.chart_type

    if chart == "scorecard":
        f = spec.wells["value"][0]
        col_alias = f.alias or _default_alias(f)
        builder.select.append(_render_aggregated(f, alias=col_alias, builder=builder, ctx=ctx))
        return ChartConfig(
            type="scorecard",
            config={
                "value_column": col_alias,
                "value_format": f.format,
                "value_label": f.column,
            },
        )

    if chart == "stat_group":
        out_cols: list[str] = []
        formats: dict[str, str] = {}
        labels: dict[str, str] = {}
        for f in spec.wells["values"]:
            alias = f.alias or _default_alias(f)
            out_cols.append(alias)
            if f.format:
                formats[alias] = f.format
            labels[alias] = f.column
            builder.select.append(_render_aggregated(f, alias=alias, builder=builder, ctx=ctx))
        return ChartConfig(
            type="stat_group",
            config={
                "value_columns": out_cols,
                "value_formats": formats,
                "value_labels": labels,
            },
        )

    if chart in ("bar", "pie", "line"):
        axis = spec.wells["axis"][0]
        value = spec.wells["values"][0]
        legend = spec.wells.get("legend") or []
        if axis.agg is not None:
            raise SpecCompileError(
                f"Axis field on {chart} chart must be raw (no aggregation)."
            )
        axis_alias = axis.alias or axis.column
        value_alias = value.alias or _default_alias(value)

        axis_qcol = _qual_col(axis, builder, ctx)
        builder.select.append(f"{axis_qcol} AS {_quote_ident(axis_alias)}")
        if legend:
            lf = legend[0]
            if lf.agg is not None:
                raise SpecCompileError("Legend field cannot be aggregated.")
            legend_alias = lf.alias or lf.column
            legend_qcol = _qual_col(lf, builder, ctx)
            builder.select.append(f"{legend_qcol} AS {_quote_ident(legend_alias)}")
            builder.group_by.append(legend_qcol)
        else:
            legend_alias = None

        builder.select.append(_render_aggregated(value, alias=value_alias, builder=builder, ctx=ctx))
        builder.group_by.insert(0, axis_qcol)

        # Sort: line charts prefer ascending axis (chronological);
        # bar / pie default to descending value (Power BI parity).
        if axis.sort:
            builder.order_by.append(f"{axis_qcol} {axis.sort.upper()}")
        elif chart == "line":
            builder.order_by.append(f"{axis_qcol} ASC")
        else:
            builder.order_by.append(f"{_render_agg_expr(value, builder=builder, ctx=ctx)} DESC")

        cfg: dict[str, Any] = {}
        if chart == "line":
            cfg["x_column"] = axis_alias
            cfg["y_column"] = value_alias
        else:
            cfg["category_column"] = axis_alias
            cfg["value_column"] = value_alias
        if legend_alias:
            cfg["legend_column"] = legend_alias
        cfg["x_label"] = axis.column
        cfg["y_label"] = value.column
        if value.format:
            cfg["value_format"] = value.format
        return ChartConfig(type=chart, config=cfg)

    if chart == "table":
        cols: list[str] = []
        sort_clauses: list[str] = []
        for f in spec.wells["columns"]:
            alias = f.alias or f.column
            if f.agg:
                raise SpecCompileError(
                    "Table visuals don't support aggregated columns yet — "
                    "drop the aggregation or use a stat_group instead."
                )
            qcol = _qual_col(f, builder, ctx)
            cols.append(qcol + " AS " + _quote_ident(alias))
            if f.sort:
                sort_clauses.append(f"{qcol} {f.sort.upper()}")
        builder.select.extend(cols)
        builder.order_by.extend(sort_clauses)
        return ChartConfig(type="table", config={})

    raise SpecCompileError(f"Unsupported chart_type: {chart}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_wells(spec: BuilderSpec) -> None:
    rules = _WELL_RULES.get(spec.chart_type)
    if rules is None:
        raise SpecCompileError(f"Unsupported chart_type: {spec.chart_type}")

    allowed = set(rules["required"]) | set(rules["optional"])
    seen = set(spec.wells)
    extra = seen - allowed
    if extra:
        raise SpecCompileError(
            f"{spec.chart_type} chart doesn't accept wells: {sorted(extra)}. "
            f"Allowed: {sorted(allowed)}."
        )

    for name, (lo, hi) in rules["required"].items():
        fields = spec.wells.get(name) or []
        if not (lo <= len(fields) <= hi):
            raise SpecCompileError(
                f"Well '{name}' on {spec.chart_type} requires "
                f"{lo}–{hi} field(s); got {len(fields)}."
            )
    for name, (lo, hi) in rules["optional"].items():
        fields = spec.wells.get(name) or []
        if len(fields) > hi:
            raise SpecCompileError(
                f"Well '{name}' on {spec.chart_type} accepts at most {hi} "
                f"field(s); got {len(fields)}."
            )

    # Aggregation requirement check — wells whose name is one of these
    # are aggregated; the field MUST carry an ``agg``.
    for agg_well in ("values", "value"):
        for f in spec.wells.get(agg_well) or []:
            if f.agg is None:
                raise SpecCompileError(
                    f"Field '{f.column}' in well '{agg_well}' needs an "
                    "aggregation (SUM / AVG / COUNT / MIN / MAX / "
                    "COUNT_DISTINCT)."
                )


def _ident(value: str) -> str:
    """Validate ``value`` is a safe SQL identifier and return it. Reject
    anything that doesn't match the strict regex — keeps quoting honest
    even when the input is hostile."""
    if not _IDENT_RE.match(value or ""):
        raise SpecCompileError(f"Invalid identifier: {value!r}")
    return value


def _quote_ident(name: str) -> str:
    return f"[{_ident(name)}]"


def _quote_table(schema: Optional[str], name: str) -> str:
    if schema:
        return f"{_quote_ident(schema)}.{_quote_ident(name)}"
    return _quote_ident(name)


def _default_alias(f: BuilderField) -> str:
    """Default result-column alias for an aggregated field. Stable so
    chart_config can reference it across re-compiles."""
    if not f.agg:
        return f.column
    if f.agg == "COUNT":
        return f"{f.column}_count"
    if f.agg == "COUNT_DISTINCT":
        return f"{f.column}_distinct_count"
    return f"{f.column}_{f.agg.lower()}"


def _render_agg_expr(
    f: BuilderField, *,
    builder: Optional[_SqlBuilder] = None,
    ctx: Optional[_CompileCtx] = None,
) -> str:
    """Just the aggregation expression — no AS alias. Used in
    ORDER BY so sorts hit the same expression as the SELECT clause.

    When ``builder`` and ``ctx`` are supplied, the column reference is
    auto-qualified with the table that owns it (and a LEFT JOIN is
    added when the field belongs to a related table). Without them,
    the column is rendered bare — that path is only reachable from
    legacy callers (no production code does this anymore)."""
    col = _qual_col(f, builder, ctx) if (builder and ctx) else _quote_ident(f.column)
    if f.agg == "COUNT":
        return f"COUNT({col})"
    if f.agg == "COUNT_DISTINCT":
        return f"COUNT(DISTINCT {col})"
    if f.agg in ("SUM", "AVG", "MIN", "MAX"):
        return f"{f.agg}({col})"
    raise SpecCompileError(f"Unknown aggregation: {f.agg!r}")


def _render_aggregated(
    f: BuilderField, *, alias: str,
    builder: Optional[_SqlBuilder] = None,
    ctx: Optional[_CompileCtx] = None,
) -> str:
    return f"{_render_agg_expr(f, builder=builder, ctx=ctx)} AS {_quote_ident(alias)}"


# ---------------------------------------------------------------------------
# Column qualification + auto-join (Phase F)
# ---------------------------------------------------------------------------

def _qual_col(
    f: BuilderField, builder: _SqlBuilder, ctx: _CompileCtx,
) -> str:
    """Resolve a BuilderField to a fully-qualified ``[table].[column]``
    SQL token. When the field's ``table`` differs from the source,
    walk the relationship graph and auto-emit ``LEFT JOIN`` clauses
    so the column is reachable.

    Phase G — when derived columns wrapped the source in a CTE, all
    source-table refs (including derived aliases) qualify via the
    CTE alias instead of the physical schema/table.

    Falls back to the source table when ``table`` is omitted."""
    # Reference to a derived alias — always lives on the CTE. Skip
    # the join machinery; the CTE is implicitly "joined" already.
    if f.column in ctx.derived_aliases and (f.table is None or f.table == ctx.source_table):
        _ident(f.column)
        return _qual_col_str(None, ctx.source_alias or ctx.source_table, f.column)

    target_table = f.table or ctx.source_table
    target_schema = f.table_schema or (
        ctx.source_schema if (f.table is None or f.table == ctx.source_table) else None
    )
    _ident(target_table)
    if target_schema:
        _ident(target_schema)

    # Source-table reference + CTE wrap → use the alias.
    if (target_table == ctx.source_table
            and (target_schema or "") == (ctx.source_schema or "")
            and ctx.source_alias):
        return _qual_col_str(None, ctx.source_alias, f.column)

    _ensure_joined(builder, ctx, target_schema, target_table)
    return _qual_col_str(target_schema, target_table, f.column)


def _qual_col_str(schema: Optional[str], table: str, column: str) -> str:
    """Emit ``[schema].[table].[column]`` (or ``[table].[column]`` when
    schema is null). Each identifier is validated through ``_ident``
    so we never produce unsafe SQL."""
    return f"{_quote_table(schema, table)}.{_quote_ident(column)}"


def _ensure_joined(
    builder: _SqlBuilder, ctx: _CompileCtx,
    schema: Optional[str], table: str,
) -> None:
    """Add a ``LEFT JOIN`` chain so ``table`` is reachable from the
    source. No-op if the table is already in the join chain."""
    key = (schema or "", table)
    if key in builder.joined_tables:
        return

    path = _find_join_path(
        ctx.relationships,
        from_schema=ctx.source_schema, from_table=ctx.source_table,
        to_schema=schema, to_table=table,
    )
    if path is None:
        raise SpecCompileError(
            f"No relationship path from {ctx.source_table!r} to {table!r}. "
            "Define the join in Schema Explorer → Relationships, or pick "
            "a column from the source table."
        )

    # Walk the path edge by edge, joining each new table along the way.
    current_table = (ctx.source_schema or "", ctx.source_table)
    for edge in path:
        a = (edge.from_schema or "", edge.from_table)
        b = (edge.to_schema or "", edge.to_table)
        # Each edge connects ``a`` and ``b``; whichever is *not* the
        # current_table is the next hop we need to JOIN in.
        next_table = b if a == current_table else a
        if next_table in builder.joined_tables:
            current_table = next_table
            continue
        # Build the ``ON`` clause from the edge's column pair. Phase G
        # — when the source is CTE-wrapped, qualify references to the
        # source side via the alias instead of the physical table.
        from_qual = _qual_col_with_alias(
            edge.from_schema, edge.from_table, edge.from_column, ctx,
        )
        to_qual = _qual_col_with_alias(
            edge.to_schema, edge.to_table, edge.to_column, ctx,
        )
        join_on = f"{from_qual} = {to_qual}"
        builder.joins.append(
            f"LEFT JOIN {_quote_table(next_table[0] or None, next_table[1])} ON {join_on}"
        )
        builder.joined_tables.add(next_table)
        current_table = next_table


def _qual_col_with_alias(
    schema: Optional[str], table: str, column: str, ctx: _CompileCtx,
) -> str:
    """Like ``_qual_col_str`` but rewrites the source table to the CTE
    alias when one is in effect. Used inside JOIN ON clauses where
    the source side might be either physical or aliased."""
    if (table == ctx.source_table
            and (schema or "") == (ctx.source_schema or "")
            and ctx.source_alias):
        return _qual_col_str(None, ctx.source_alias, column)
    return _qual_col_str(schema, table, column)


def _find_join_path(
    relationships: list, *,
    from_schema: Optional[str], from_table: str,
    to_schema: Optional[str], to_table: str,
    max_depth: int = 4,
) -> Optional[list]:
    """BFS over the relationship graph for the shortest path between
    two tables. Direction-agnostic — edges are bidirectional from a
    join standpoint. Returns the list of edges, or ``None`` when no
    path exists within ``max_depth`` hops."""
    src = (from_schema or "", from_table)
    dst = (to_schema or "", to_table)
    if src == dst:
        return []

    adj: dict = {}
    for r in relationships:
        if not getattr(r, "is_active", True):
            continue
        a = (r.from_schema or "", r.from_table)
        b = (r.to_schema or "", r.to_table)
        adj.setdefault(a, []).append((b, r))
        adj.setdefault(b, []).append((a, r))

    queue: list = [(src, [])]
    visited = {src}
    while queue:
        node, path = queue.pop(0)
        if len(path) > max_depth:
            continue
        for neighbor, edge in adj.get(node, []):
            if neighbor in visited:
                continue
            new_path = path + [edge]
            if neighbor == dst:
                return new_path
            visited.add(neighbor)
            queue.append((neighbor, new_path))
    return None


# ---------------------------------------------------------------------------
# Filter rendering
# ---------------------------------------------------------------------------

_SCALAR_OPS = {"=", "!=", ">", ">=", "<", "<=", "like", "not_like"}


def _render_aggregate_filter(
    af: AggregateFilter, *,
    builder: _SqlBuilder, ctx: _CompileCtx,
) -> str:
    """Phase G.2 — emit one HAVING predicate. Builds the aggregate
    expression via the same path as the SELECT-side aggregator so the
    HAVING text matches the SELECT text exactly (portable across
    engines, regardless of whether they resolve by alias or expr)."""
    # Construct a synthetic BuilderField so ``_render_agg_expr`` can
    # do the column qualification + auto-join machinery for us. The
    # column on an AggregateFilter always lives on the source (or a
    # derived alias) — joined-table aggregate filters can come later.
    proxy = BuilderField(column=af.column, agg=af.agg)
    agg_expr = _render_agg_expr(proxy, builder=builder, ctx=ctx)
    op = af.op
    if op == "is_null":
        return f"{agg_expr} IS NULL"
    if op == "is_not_null":
        return f"{agg_expr} IS NOT NULL"
    if op in _SCALAR_OPS:
        sql_op = {"like": "LIKE", "not_like": "NOT LIKE"}.get(op, op)
        return f"{agg_expr} {sql_op} {_render_literal(af.value)}"
    if op in ("in", "not_in"):
        if not isinstance(af.value, (list, tuple)) or not af.value:
            raise SpecCompileError(
                f"Aggregate filter on {af.agg}({af.column}) needs a non-empty list.",
            )
        items = ", ".join(_render_literal(v) for v in af.value)
        sql_op = "IN" if op == "in" else "NOT IN"
        return f"{agg_expr} {sql_op} ({items})"
    if op == "between":
        if not isinstance(af.value, (list, tuple)) or len(af.value) != 2:
            raise SpecCompileError(
                f"Aggregate filter on {af.agg}({af.column}) 'between' "
                "needs a 2-element [lo, hi] list.",
            )
        lo, hi = af.value
        return f"{agg_expr} BETWEEN {_render_literal(lo)} AND {_render_literal(hi)}"
    raise SpecCompileError(f"Unknown aggregate-filter op: {op!r}")


def _render_filter(
    f: BuilderFilter,
    *,
    source_schema: Optional[str] = None,
    source_table: Optional[str] = None,
    source_alias: Optional[str] = None,
) -> str:
    # Filters always bind to source-table columns for now (or derived
    # aliases living on the CTE — same physical row). Cross-table
    # filtering can come later as a separate ``table`` field on
    # BuilderFilter, mirroring BuilderField.
    if source_alias:
        col = _qual_col_str(None, source_alias, f.column)
    elif source_table:
        col = _qual_col_str(source_schema, source_table, f.column)
    else:
        col = _quote_ident(f.column)
    op = f.op

    if op == "is_null":
        return f"{col} IS NULL"
    if op == "is_not_null":
        return f"{col} IS NOT NULL"

    if op in _SCALAR_OPS:
        sql_op = {"like": "LIKE", "not_like": "NOT LIKE"}.get(op, op)
        return f"{col} {sql_op} {_render_literal(f.value)}"

    if op in ("in", "not_in"):
        if not isinstance(f.value, (list, tuple)) or not f.value:
            raise SpecCompileError(f"Filter '{f.column} {op}' needs a non-empty list.")
        items = ", ".join(_render_literal(v) for v in f.value)
        sql_op = "IN" if op == "in" else "NOT IN"
        return f"{col} {sql_op} ({items})"

    if op == "between":
        if not isinstance(f.value, (list, tuple)) or len(f.value) != 2:
            raise SpecCompileError(
                f"Filter '{f.column} between' needs a 2-element [lo, hi] list."
            )
        lo, hi = f.value
        return f"{col} BETWEEN {_render_literal(lo)} AND {_render_literal(hi)}"

    raise SpecCompileError(f"Unknown filter op: {op!r}")


# Phase I — runtime parameters the API auto-binds on every KPI run.
# A filter value of {"$param": "company_id"} compiles to the bare
# bind marker ``:company_id`` instead of an inlined literal, so the
# same KPI auto-slices per caller. Strict allow-list: any other
# ``$param`` name is rejected at compile time so a malicious spec
# can't conjure a placeholder the executor doesn't bind.
_RUNTIME_PARAMS = frozenset((
    "start_date", "end_date", "company_id", "user_id",
))


def _is_param_ref(v: Any) -> Optional[str]:
    """Detect a ``{"$param": "name"}`` dict. Returns the name (when
    valid + allow-listed), else ``None``."""
    if isinstance(v, dict) and len(v) == 1 and "$param" in v:
        name = v.get("$param")
        if not isinstance(name, str):
            raise SpecCompileError("$param must be a string.")
        if name not in _RUNTIME_PARAMS:
            raise SpecCompileError(
                f"Unknown runtime parameter: {name!r}. "
                f"Allowed: {sorted(_RUNTIME_PARAMS)}.",
            )
        return name
    return None


def _render_literal(v: Any) -> str:
    """Convert a Python value into a safe SQL literal token. T-SQL only
    for now — strings use ``N'…'`` (Unicode) with single-quote doubling.
    Lists are NOT supported here (callers handle list-shaped operators
    like ``in`` / ``between`` themselves).

    Phase I — a value of ``{"$param": "company_id"}`` compiles to
    ``:company_id`` (a runtime bind marker), not an inlined literal,
    so the executor's auto-bound runtime context is used."""
    param = _is_param_ref(v)
    if param is not None:
        return f":{param}"
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(int(v))
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):  # NaN / inf
            raise SpecCompileError(f"Non-finite numeric value: {v}")
        return repr(float(v))
    if isinstance(v, datetime):
        # ISO 8601 — SQL Server accepts this format directly.
        return f"N'{v.replace(microsecond=0).isoformat()}'"
    if isinstance(v, date):
        return f"N'{v.isoformat()}'"
    if isinstance(v, str):
        escaped = v.replace("'", "''")
        return f"N'{escaped}'"
    raise SpecCompileError(f"Unsupported literal type: {type(v).__name__}")


__all__ = [
    "compile_spec",
    "SpecCompileError",
]
