"""Pydantic request/response models for kpi_studio."""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Schema introspection payload — what the introspector produces and what
# /schema/* endpoints return.
# ---------------------------------------------------------------------------

class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool = False
    default: Optional[str] = None
    autoincrement: bool = False
    comment: Optional[str] = None


class ForeignKeyInfo(BaseModel):
    constrained_columns: List[str]
    referred_schema: Optional[str] = None
    referred_table: str
    referred_columns: List[str]
    name: Optional[str] = None


class IndexInfo(BaseModel):
    name: str
    columns: List[str]
    unique: bool


class TableInfo(BaseModel):
    schema_name: Optional[str] = Field(default=None, alias="schema")
    name: str
    comment: Optional[str] = None
    columns: List[ColumnInfo] = Field(default_factory=list)
    primary_key: List[str] = Field(default_factory=list)
    foreign_keys: List[ForeignKeyInfo] = Field(default_factory=list)
    indexes: List[IndexInfo] = Field(default_factory=list)
    row_count_estimate: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class SchemaPayload(BaseModel):
    """Full introspection result for a target DB."""
    dialect: str
    database_key: str
    introspected_at: datetime
    tables: List[TableInfo]


class GraphNode(BaseModel):
    id: str  # "schema.table" — stable across reloads
    label: str
    schema_name: Optional[str] = Field(default=None, alias="schema")
    column_count: int

    model_config = ConfigDict(populate_by_name=True)


class GraphEdge(BaseModel):
    source: str  # constrained side (foreign key holder)
    target: str  # referenced table
    columns: List[str]
    name: Optional[str] = None


class SchemaGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class SchemaSnapshotMeta(BaseModel):
    snapshot_id: int
    database_key: str
    table_count: int
    relationship_count: int
    created_at: datetime
    created_by: Optional[int] = None
    is_current: bool


class SchemaListResponse(BaseModel):
    snapshot: SchemaSnapshotMeta
    tables: List[TableInfo]


class SchemaRefreshResponse(BaseModel):
    snapshot: SchemaSnapshotMeta
    refreshed: bool


# ---------------------------------------------------------------------------
# Phase F — Data modeling (table relationships)
# ---------------------------------------------------------------------------

RelationshipCardinality = Literal["many_to_one", "one_to_one", "one_to_many"]
RelationshipSource = Literal["auto", "manual"]


class TableRelationshipPayload(BaseModel):
    """One join edge — the ``from`` side holds the FK, the ``to`` side
    is the parent. Cardinality is informational; the spec compiler
    treats every edge as a candidate for ``LEFT JOIN``."""
    relationship_id: int
    company_id: Optional[int] = None
    from_schema: Optional[str] = None
    from_table: str
    from_column: str
    to_schema: Optional[str] = None
    to_table: str
    to_column: str
    cardinality: RelationshipCardinality = "many_to_one"
    source: RelationshipSource = "auto"
    is_active: bool = True


class TableRelationshipCreate(BaseModel):
    from_schema: Optional[str] = Field(default=None, max_length=64)
    from_table: str = Field(..., min_length=1, max_length=128)
    from_column: str = Field(..., min_length=1, max_length=128)
    to_schema: Optional[str] = Field(default=None, max_length=64)
    to_table: str = Field(..., min_length=1, max_length=128)
    to_column: str = Field(..., min_length=1, max_length=128)
    cardinality: RelationshipCardinality = "many_to_one"


class TableRelationshipListResponse(BaseModel):
    items: List[TableRelationshipPayload]
    total: int


class TableRelationshipAutoSeedResponse(BaseModel):
    """Returned by ``POST /schema/relationships/auto-seed`` — counts so
    a SuperAdmin can verify the introspector picked up FK metadata."""
    inserted: int
    skipped: int
    total_active: int


# ---------------------------------------------------------------------------
# Phase A1 — KPI authoring + execution
# ---------------------------------------------------------------------------

class ChartConfig(BaseModel):
    """Renderer-specific payload. ``type`` drives which other fields apply.

    ``style`` is an open-ended dict (Phase A6) — keys recognised by the
    frontend renderer right now: ``theme`` (default/dark/vibrant/minimal),
    ``animations`` (bool). Stored as JSON so adding new style knobs later
    doesn't need a migration.
    """
    type: str = Field(..., description="One of scorecard|stat_group|bar|line|pie|table")
    config: dict[str, Any] = Field(default_factory=dict)
    style: dict[str, Any] = Field(default_factory=dict)


class ChartSuggestion(BaseModel):
    type: str
    config: dict[str, Any]
    reason: str = ""
    alternates: List[str] = Field(default_factory=list)


class ExecutionResultPayload(BaseModel):
    """Wire shape returned by /preview and /run."""
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    rewritten_sql: str
    notes: List[str] = Field(default_factory=list)
    suggestion: Optional[ChartSuggestion] = None


# ---- KPI requests/responses ----------------------------------------------

# ---------------------------------------------------------------------------
# Smart Builder — Power BI–style "drag-fields-into-wells" authoring (Phase C)
#
# A ``BuilderSpec`` is the source of truth when a KPI is authored visually.
# The compiler turns it into deterministic SQL + a chart_config payload, so
# round-tripping through the editor never drifts from what runs at execute
# time. Raw-SQL KPIs (``builder_spec=None``) keep working unchanged.
# ---------------------------------------------------------------------------

# Aggregations the wells UI exposes — same vocabulary as Power BI's
# field menu. ``COUNT_DISTINCT`` deliberately uses underscore so the
# wire shape stays a single token (the compiler emits ``COUNT(DISTINCT …)``).
BuilderAggregation = Literal[
    "SUM", "AVG", "COUNT", "COUNT_DISTINCT", "MIN", "MAX",
]

BuilderFormat = Literal["number", "currency", "percent", "date", "text"]

BuilderSortDir = Literal["asc", "desc"]

BuilderFilterOp = Literal[
    "=", "!=", ">", ">=", "<", "<=",
    "in", "not_in",
    "like", "not_like",
    "is_null", "is_not_null",
    "between",
]

BuilderChartType = Literal[
    "scorecard", "stat_group", "bar", "pie", "line", "table",
]


class BuilderSource(BaseModel):
    """Where the visual reads from. Phase C ships ``table`` only; future
    phases add ``dataset`` (a saved KPI used as a virtual table) and
    cross-table joins via ``BuilderJoin`` objects."""
    kind: Literal["table"] = "table"
    schema_name: Optional[str] = Field(
        default=None, alias="schema",
        description="Optional SQL schema (e.g. dbo) — quoted into the FROM clause.",
    )
    name: str = Field(..., min_length=1, max_length=128)

    model_config = ConfigDict(populate_by_name=True)


class BuilderField(BaseModel):
    """A column reference plus per-well options. ``agg`` is required on
    aggregated wells (values, scorecard.value) and forbidden on raw
    wells (axis on bar/line, columns on table) — enforced by the
    compiler since the rule is chart-type-specific.

    Phase F — ``table`` lets a field reference a column from a
    *related* table (e.g. ``customers.name`` while the source is
    ``enquiries``). The compiler walks the relationship graph and
    auto-emits the LEFT JOIN. When ``table`` is omitted the column
    lives on the source table.
    """
    column: str = Field(..., min_length=1, max_length=128)
    table: Optional[str] = Field(default=None, max_length=128)
    table_schema: Optional[str] = Field(default=None, alias="schema", max_length=64)
    agg: Optional[BuilderAggregation] = None
    format: Optional[BuilderFormat] = None
    sort: Optional[BuilderSortDir] = None
    alias: Optional[str] = Field(default=None, max_length=128)

    model_config = ConfigDict(populate_by_name=True)


class BuilderFilter(BaseModel):
    """Dataset-wide filter — translated into one WHERE predicate.

    ``value`` shape depends on ``op``:
      * single-value ops (=, !=, >, etc.) → scalar
      * ``in`` / ``not_in``               → list
      * ``between``                        → 2-element list [low, high]
      * ``is_null`` / ``is_not_null``      → ignored (omit the field)
    """
    column: str = Field(..., min_length=1, max_length=128)
    op: BuilderFilterOp
    value: Any = None


class AggregateFilter(BaseModel):
    """Phase G.2 — predicate on an *aggregated* value, emitted as a
    ``HAVING`` clause. Distinct from ``BuilderFilter`` because:
      * BuilderFilter (WHERE) runs *before* aggregation — filters
        the rows that get summed/counted.
      * AggregateFilter (HAVING) runs *after* aggregation — keeps
        groups whose aggregate meets the predicate.

    Example: ``SUM(amount) > 100000`` keeps only categories whose
    total exceeds 1L. Same operator vocabulary as BuilderFilter so
    the UI can reuse the operator picker.
    """
    column: str = Field(..., min_length=1, max_length=128)
    agg: BuilderAggregation
    op: BuilderFilterOp
    value: Any = None


class DerivedColumn(BaseModel):
    """Phase G — a calculated column the user defines once and uses
    everywhere (wells, filters, sorts) like a regular column.

    The compiler wraps the source table in a CTE so the expression
    only evaluates once per row, and downstream references resolve
    against the alias rather than re-evaluating the SQL.

    ``expression`` is a free-form T-SQL expression that gets pasted
    inline into ``SELECT ... AS [alias]``. The downstream sql_safety
    validator catches DDL/DML attempts; the alias is identifier-
    validated up-front so it can't escape its slot.
    """
    alias: str = Field(..., min_length=1, max_length=128)
    expression: str = Field(..., min_length=1, max_length=4000)
    description: Optional[str] = Field(default=None, max_length=500)
    format: Optional[BuilderFormat] = None


class BuilderSpec(BaseModel):
    """Top-level builder spec. ``wells`` is keyed by well-name —
    ``axis`` / ``values`` / ``legend`` / ``columns`` / ``value`` —
    and the legal set is chart-type-dependent (compiler validates).
    Everything else is shared knobs that apply across visual types."""
    chart_type: BuilderChartType
    source: BuilderSource
    wells: dict[str, List[BuilderField]] = Field(default_factory=dict)
    filters: List[BuilderFilter] = Field(default_factory=list)
    top_n: Optional[int] = Field(default=None, ge=1, le=10_000)
    # Same time-binding semantics as raw-SQL KPIs — when set, the
    # compiler injects a ``BETWEEN :start_date AND :end_date`` predicate
    # against this column so the dashboard's period selector works.
    time_column: Optional[str] = Field(default=None, max_length=128)
    # Phase G — calculated columns. Each is added to a CTE wrapping
    # the source so any well or filter can reference its alias just
    # like a real column. Empty list = no transform; same SQL as before.
    derived_columns: List[DerivedColumn] = Field(default_factory=list)
    # Phase G.2 — predicates on aggregated values (HAVING clause).
    # Filters here run *after* GROUP BY, so they can reference
    # SUM(amount), COUNT(*), etc. directly.
    aggregate_filters: List[AggregateFilter] = Field(default_factory=list)


class CompiledSpec(BaseModel):
    """What the compiler returns. ``sql`` is ready for the executor +
    safety validator; ``chart_config`` is the matching renderer payload."""
    sql: str
    chart_config: ChartConfig
    notes: List[str] = Field(default_factory=list)


class KpiPreviewRequest(BaseModel):
    """Run an unsaved query and get back a chart suggestion.

    Two modes mirror the create/update API:
      * **Raw**: caller sends ``query_text``.
      * **Builder**: caller sends ``builder_spec`` and the server
        compiles it on the fly. The compiled SQL is returned alongside
        the result via ``rewritten_sql`` so the editor can show it.
    """
    query_text: Optional[str] = Field(default=None, min_length=1, max_length=20_000)
    builder_spec: Optional[BuilderSpec] = None
    database_key: str = "primary"
    # Phase A5 — optional time-period filter. ``period`` is a preset name
    # (daily / weekly / monthly / quarterly / yearly / last_5_years /
    # custom). For ``custom`` both ``start_date`` and ``end_date`` must be
    # supplied. Server-side conversion happens in services/time_periods.py.
    period: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @model_validator(mode="after")
    def _require_builder_or_query(self):
        if self.builder_spec is None and not self.query_text:
            raise ValueError("Provide either builder_spec or query_text.")
        return self


class KpiRunRequest(BaseModel):
    """Body for ``POST /kpis/{id}/run`` — same period shape as preview.

    Phase J.2 — ``extra_filters`` lets a dashboard card slice the KPI
    further at execute time without forking the definition. Only honored
    when the saved KPI has a builder_spec (so we can recompile cleanly);
    raw-SQL KPIs ignore extras since there's no safe place to insert
    them after the fact.
    """
    period: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    extra_filters: List[BuilderFilter] = Field(default_factory=list)


class KpiCreateRequest(BaseModel):
    """Two authoring modes:
      * **Builder mode** — caller sends ``builder_spec``. Server compiles
        it to SQL + chart_config; ``query_text``/``chart_config`` may be
        omitted (any values sent are overwritten by the compiled output).
      * **Raw SQL mode** — caller sends ``query_text`` + ``chart_config``
        directly (legacy path). ``builder_spec`` stays null.
    Exactly one of the two paths is used per request; mixing is allowed
    only when builder mode is active (raw fields are ignored)."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    query_text: Optional[str] = Field(default=None, min_length=1, max_length=20_000)
    chart_config: Optional[ChartConfig] = None
    database_key: str = "primary"
    # Optional column the time-period selector filters on. ``None`` =
    # KPI ignores the global time selector.
    time_column: Optional[str] = Field(default=None, max_length=100)
    builder_spec: Optional[BuilderSpec] = None

    @model_validator(mode="after")
    def _require_builder_or_sql(self):
        if self.builder_spec is None and not self.query_text:
            raise ValueError("Provide either builder_spec or query_text.")
        return self


class KpiUpdateRequest(BaseModel):
    """Saves a new version. ``name``/``description`` may be patched on
    the definition itself; ``query_text``/``chart_config``/``time_column``/
    ``builder_spec`` always create a new version row.

    Mode-switching is allowed: a builder-mode KPI can be patched with
    just ``query_text`` to drop the spec and become raw-SQL, or vice-versa
    by sending a fresh ``builder_spec``."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    query_text: Optional[str] = Field(default=None, min_length=1, max_length=20_000)
    chart_config: Optional[ChartConfig] = None
    database_key: Optional[str] = None
    time_column: Optional[str] = Field(default=None, max_length=100)
    builder_spec: Optional[BuilderSpec] = None


class KpiVersionSummary(BaseModel):
    version_id: int
    version_no: int
    chart_type: str
    created_at: datetime
    created_by: Optional[int] = None


class KpiSummary(BaseModel):
    """Lightweight row for the KPI list."""
    kpi_id: int
    name: str
    description: Optional[str] = None
    chart_type: str
    current_version_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    company_id: Optional[int] = None
    is_active: bool
    updated_at: datetime


class KpiDetail(BaseModel):
    """Full KPI shape — includes the current version's authoring state."""
    kpi_id: int
    name: str
    description: Optional[str] = None
    company_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    current_version_id: Optional[int] = None
    query_text: Optional[str] = None
    chart_config: Optional[ChartConfig] = None
    database_key: str = "primary"
    time_column: Optional[str] = None
    # Phase C — present when the KPI was authored via the smart builder.
    # Frontend uses this to round-trip back into the wells UI; absent
    # means raw-SQL mode and the editor opens straight on the textarea.
    builder_spec: Optional[BuilderSpec] = None
    versions: List[KpiVersionSummary] = Field(default_factory=list)


class KpiListResponse(BaseModel):
    items: List[KpiSummary]
    total: int


# ---------------------------------------------------------------------------
# Phase A2 — Dashboards
# ---------------------------------------------------------------------------

DASHBOARD_SCOPES = ("user", "company")
DASHBOARD_CARD_SIZES = ("sm", "md", "lg", "wide")

# Phase J.2 — vocabulary for the per-card animation overrides. The frontend
# maps these onto CSS keyframes (kpi-card-enter etc.). The decorator's
# system prompt also hard-codes this list so the LLM can't invent values.
DASHBOARD_ANIMATIONS = ("fade", "slide", "scale", "none")


class DashboardItemPayload(BaseModel):
    """One item on a dashboard. Matches ``KpiDashboardItem`` plus the KPI's
    summary so the frontend can render header + chart-type without a second
    round-trip.

    ``kpi_chart_config`` is the full saved chart payload (type + config +
    style). Cards use this to render exactly what the author chose; the
    live executor's auto-suggestion is reserved as a fallback for
    legacy KPIs that pre-date the saved config.

    ``grid_x/y/w/h`` are Phase D Power BI–style coordinates. The API
    always populates them — backfilling from ``position`` + ``size_class``
    when the row predates the migration — so the frontend can drive
    angular-gridster2 without a null-check.
    """
    item_id: int
    kpi_id: int
    kpi_name: str
    kpi_chart_type: str
    kpi_chart_config: Optional[ChartConfig] = None
    kpi_is_active: bool
    position: int
    size_class: str
    grid_x: int = 0
    grid_y: int = 0
    grid_w: int = 6
    grid_h: int = 4
    title_override: Optional[str] = None
    # Phase J.2 — per-card visual + filter overrides set by AI Polish.
    # Empty / None means "use the KPI's own defaults".
    icon: Optional[str] = Field(default=None, max_length=64)
    animation_in: Optional[str] = Field(default=None, max_length=16)
    animation_out: Optional[str] = Field(default=None, max_length=16)
    # Per-card axis labels for bar / line charts. None falls back to the
    # KPI's chart_config x_label / y_label (which itself can be empty).
    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)
    extra_filters: List[BuilderFilter] = Field(default_factory=list)


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    scope: str = Field(default="user", description="One of: user, company")


class DashboardUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    scope: Optional[str] = Field(default=None)


class DashboardItemCreate(BaseModel):
    kpi_id: int
    size_class: str = Field(default="md")
    title_override: Optional[str] = Field(default=None, max_length=200)


class DashboardItemUpdate(BaseModel):
    size_class: Optional[str] = None
    title_override: Optional[str] = Field(default=None, max_length=200)
    # Phase J.2 — per-card visual + filter overrides. Sentinel ``""``
    # means "clear the override"; ``None`` means "leave unchanged".
    icon: Optional[str] = Field(default=None, max_length=64)
    animation_in: Optional[str] = Field(default=None, max_length=16)
    animation_out: Optional[str] = Field(default=None, max_length=16)
    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)
    extra_filters: Optional[List[BuilderFilter]] = None


class DashboardLayoutEntry(BaseModel):
    """One entry in the bulk-layout PUT — the drag-drop end-of-drop payload.

    Phase D adds grid coordinates. ``position`` is still accepted (drives
    legacy back-compat) but coords win when both are sent — that's how
    angular-gridster2 communicates the new placement.

    Phase J.2 — also accepts visual overrides so AI Polish can persist
    sizes + icons + animations + filters in a single round trip.
    """
    item_id: int
    position: int
    size_class: Optional[str] = None
    # 24-column grid (Phase D refinement) — twice as fine as the
    # original 12-col layout so drag/resize jumps in finer increments.
    grid_x: Optional[int] = Field(default=None, ge=0, le=23)
    grid_y: Optional[int] = Field(default=None, ge=0, le=1999)
    grid_w: Optional[int] = Field(default=None, ge=1, le=24)
    grid_h: Optional[int] = Field(default=None, ge=1, le=48)
    title_override: Optional[str] = Field(default=None, max_length=200)
    icon: Optional[str] = Field(default=None, max_length=64)
    animation_in: Optional[str] = Field(default=None, max_length=16)
    animation_out: Optional[str] = Field(default=None, max_length=16)
    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)
    extra_filters: Optional[List[BuilderFilter]] = None


class DashboardLayoutRequest(BaseModel):
    items: List[DashboardLayoutEntry]


class DashboardSummary(BaseModel):
    """Lightweight row for the dashboard list."""
    dashboard_id: int
    name: str
    description: Optional[str] = None
    scope: str
    owner_user_id: Optional[int] = None
    company_id: Optional[int] = None
    is_active: bool
    item_count: int
    updated_at: datetime


class DashboardDetail(BaseModel):
    """Full dashboard shape with items + their KPI metadata."""
    dashboard_id: int
    name: str
    description: Optional[str] = None
    scope: str
    owner_user_id: Optional[int] = None
    company_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    items: List[DashboardItemPayload] = Field(default_factory=list)


class DashboardListResponse(BaseModel):
    items: List[DashboardSummary]
    total: int


# ---- Assignments (Phase A4) ----------------------------------------------

class DashboardAssignmentCreate(BaseModel):
    """Grant access to one role OR one user — never both in the same row."""
    role_id: Optional[int] = None
    user_id: Optional[int] = None

    @model_validator(mode="after")
    def _exactly_one_target(self):
        # XOR: precisely one of (role_id, user_id) must be set. Anything
        # else (both/neither) is rejected at the API edge.
        has_role = self.role_id is not None
        has_user = self.user_id is not None
        if has_role == has_user:
            raise ValueError(
                "Provide exactly one of role_id or user_id — not both, not neither."
            )
        return self


class DashboardAssignmentInfo(BaseModel):
    """Wire shape for listing assignees on a dashboard.

    Names are NOT joined here — kpi_studio stays free of host-table imports.
    The frontend resolves names via /api/v1/roles and /api/v1/users.
    """
    assignment_id: int
    dashboard_id: int
    role_id: Optional[int] = None
    user_id: Optional[int] = None
    granted_by: Optional[int] = None
    granted_at: datetime


# ---------------------------------------------------------------------------
# Phase A3 — NL → SQL
# ---------------------------------------------------------------------------

class NlValidation(BaseModel):
    """Result of running the safety validator against generated SQL."""
    ok: bool
    message: Optional[str] = None
    findings: List[str] = Field(default_factory=list)
    rewritten_sql: Optional[str] = None
    """The post-validator SQL (with TOP injected etc.). Empty when validation
    failed — the user sees the original generated SQL in that case."""


class NlGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    # ``agent`` (default) runs the multi-step tool-use loop;
    # ``single`` falls back to one-shot prompt → SQL.
    mode: str = Field(default="agent")


class NlAgentStep(BaseModel):
    """One observable event in an agent run — what the UI timeline shows."""
    type: str  # tool_call | tool_error | thought | final | abort
    tool: Optional[str] = None
    args: Optional[dict[str, Any]] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


class NlGenerateResponse(BaseModel):
    """NL→SQL result.

    The frontend always shows ``sql`` to the user for review before any
    execution happens. ``validation`` lets the editor surface a warning
    inline ("model produced invalid SQL — try rephrasing").

    ``mode`` and ``steps`` (Phase A7) describe how the answer was reached.
    Single-shot mode returns an empty steps list.
    """
    sql: str
    explanation: str
    provider: str
    model: str
    latency_ms: int
    usage: dict[str, Any] = Field(default_factory=dict)
    validation: NlValidation
    mode: str = "single"
    steps: List[NlAgentStep] = Field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    succeeded: bool = True
    error: Optional[str] = None


class NlStatusResponse(BaseModel):
    """Discoverability endpoint. Lets the frontend hide the NL surface
    entirely when no provider is configured."""
    enabled: bool
    provider: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase J — AI suggests KPIs for a table
# ---------------------------------------------------------------------------

class KpiSuggestRequest(BaseModel):
    """Body for ``POST /ai/suggest-kpis``. ``table`` is the source
    name; ``schema`` is the optional database schema (e.g. ``dbo``).
    ``count`` is a soft hint — the LLM may return fewer if its
    proposals don't all compile."""
    table: str = Field(..., min_length=1, max_length=128)
    schema_name: Optional[str] = Field(
        default=None, alias="schema", max_length=64,
    )
    count: int = Field(default=6, ge=1, le=12)

    model_config = ConfigDict(populate_by_name=True)


class KpiSuggestionItem(BaseModel):
    """One ready-to-save proposal. The frontend previews ``sql`` +
    ``chart_config`` and POSTs ``builder_spec`` (plus name +
    description) to ``/kpis`` if the user accepts."""
    name: str
    description: str
    builder_spec: BuilderSpec
    chart_config: ChartConfig
    sql: str


class KpiSuggestResponse(BaseModel):
    items: List[KpiSuggestionItem]
    tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase J.2 — AI auto-decorate (layout proposal for an existing dashboard)
# ---------------------------------------------------------------------------

class DashboardDecorationItem(BaseModel):
    """One item's proposed placement + per-card style. The frontend
    can compare against the current layout to highlight what's about
    to change."""
    item_id: int
    grid_x: int = Field(..., ge=0, le=23)
    grid_y: int = Field(..., ge=0, le=1999)
    grid_w: int = Field(..., ge=1, le=24)
    grid_h: int = Field(..., ge=1, le=48)
    size_class: str
    title_override: Optional[str] = Field(default=None, max_length=200)
    # Phase J.2 — per-card visual + filter polish.
    icon: Optional[str] = Field(default=None, max_length=64)
    animation_in: Optional[str] = Field(default=None, max_length=16)
    animation_out: Optional[str] = Field(default=None, max_length=16)
    x_label: Optional[str] = Field(default=None, max_length=120)
    y_label: Optional[str] = Field(default=None, max_length=120)
    extra_filters: List[BuilderFilter] = Field(default_factory=list)


class DashboardDecorateResponse(BaseModel):
    """Layout proposal — returned by ``POST /dashboards/{id}/auto-decorate``.

    Caller is expected to display the proposal, let the user accept,
    and then PUT it through ``/dashboards/{id}/layout`` (plus
    per-item title updates if any). The endpoint does NOT mutate the
    dashboard itself — proposals are advisory.

    ``used_fallback`` is true when the LLM call failed and the
    rule-based packer was used instead. The placements are still
    valid and applyable; the UI should just label the result
    differently ("Auto-arranged" vs "AI-arranged")."""
    items: List[DashboardDecorationItem]
    tokens: int = 0
    latency_ms: int = 0
    model: str = ""
    error: Optional[str] = None
    used_fallback: bool = False


# ---------------------------------------------------------------------------
# Settings (Phase A7+ — runtime-editable knobs)
# ---------------------------------------------------------------------------

# Sentinel string for the API-key field meaning "leave the stored value
# alone". Anything else (including empty string) is treated as the new
# value to write — empty string clears it. We use a sentinel rather than
# making the field optional so the frontend can distinguish "user didn't
# touch the field" from "user explicitly cleared it".
KEEP_API_KEY = "__KEEP__"


class StageDefinition(BaseModel):
    """T-902: one row in the per-stage routing matrix the UI renders."""
    key: str
    label: str
    description: str
    built: bool


class SettingsResponse(BaseModel):
    """Returned by ``GET /settings``. Never includes the API key — only
    a flag so the UI can show "set" vs "not set"."""
    llm_provider: Optional[str] = None
    has_api_key: bool = False
    openai_model: Optional[str] = None
    openai_base_url: Optional[str] = None
    token_budget: Optional[int] = None
    max_iterations: Optional[int] = None
    max_tokens_per_call: Optional[int] = None
    # System Knowledge Hub — admin-curated business context appended to
    # the agent's system prompt on every chat turn.
    domain_knowledge: Optional[str] = None

    # T-901: OpenRouter extras (sent as HTTP headers when provider == 'openrouter').
    openrouter_referer: Optional[str] = None
    openrouter_app_name: Optional[str] = None

    # T-902 + multi-provider refactor: per-stage routing values can be
    # legacy strings OR {provider_config_id, model} objects.
    stage_models: Optional[dict[str, Any]] = None
    default_stage_model: Optional[str] = None
    # Stage taxonomy — echoed so the UI doesn't need a separate fetch
    # to know which stage rows to render. Stable across requests; the
    # frontend can cache it if it wants to.
    stages: list[StageDefinition] = Field(default_factory=list)
    # Resolved (effective) model per stage, after the
    # stage_models → default_stage_model → openai_model fallback chain.
    # The UI uses this to show "what would run today" alongside the
    # user's editable assignment.
    effective_stage_models: dict[str, str] = Field(default_factory=dict)

    # Effective values (after DB→env→default resolution) — what the
    # backend actually uses right now. Helps the UI show the user what
    # will run if they don't change anything.
    effective_provider: Optional[str] = None
    effective_model: Optional[str] = None
    effective_token_budget: int = 0
    effective_max_iterations: int = 0
    effective_max_tokens_per_call: int = 0
    # ``true`` when an API key is reachable from either DB or env.
    effective_has_key: bool = False
    # Whether the env var fallback is the one currently in use (i.e. no
    # DB row, or DB row's relevant column is NULL).
    using_env_fallback: bool = True

    # 2026-05-25 — current state of the automatic-healthcheck switch.
    # ``True`` (default) = PUT /settings runs probes + weekly job runs;
    # ``False`` = save commits without probes + weekly job no-ops.
    healthcheck_auto_enabled: bool = True
    # 2026-05-25 — call-log subsystem state echo.
    call_logging_enabled: bool = True
    call_log_retention_days: int = 7


class SettingsUpdate(BaseModel):
    """Body for ``PUT /settings``. All fields optional — omitted fields
    leave the stored value alone. The API-key field uses the
    ``KEEP_API_KEY`` sentinel for "no change", any other string for
    "write this value" (empty string clears)."""
    llm_provider: Optional[str] = Field(default=None, max_length=40)
    openai_api_key: str = Field(default=KEEP_API_KEY)
    openai_model: Optional[str] = Field(default=None, max_length=100)
    openai_base_url: Optional[str] = Field(default=None, max_length=500)
    token_budget: Optional[int] = Field(default=None, ge=100, le=10_000_000)
    max_iterations: Optional[int] = Field(default=None, ge=1, le=50)
    max_tokens_per_call: Optional[int] = Field(default=None, ge=100, le=200_000)
    # ``None`` means "leave alone"; an empty string explicitly clears the
    # stored value so the agent reverts to no extras block. Capped at 32 KB
    # to keep token budgets sane — the prompt is sent on every turn.
    domain_knowledge: Optional[str] = Field(default=None, max_length=32_000)

    # T-901: OpenRouter extras. Same "None = leave alone, '' = clear"
    # semantics as the other string fields.
    openrouter_referer: Optional[str] = Field(default=None, max_length=500)
    openrouter_app_name: Optional[str] = Field(default=None, max_length=200)

    # T-902 + multi-provider refactor: per-stage routing supports
    # legacy strings ("model-string") for backward compat AND the new
    # object shape ({"provider_config_id": int, "model": str}) for
    # explicit provider-config selection. Replace semantics — round-
    # trip everything you want to keep.
    stage_models: Optional[dict[str, Any]] = Field(default=None)
    default_stage_model: Optional[str] = Field(default=None, max_length=200)

    # T-004: bypass healthcheck refusal on save. Defaults False — a
    # PUT that introduces a misconfigured model gets a 400. The admin
    # can pass ``force=true`` to save anyway (audited).
    force: bool = False

    # 2026-05-25 — admin toggle for the automatic LLM-probe healthcheck.
    # ``False`` => save commits without running probes AND the weekly
    # scheduled probe job no-ops. Manual "Run health check" button
    # still works. Cost kill switch.
    healthcheck_auto_enabled: Optional[bool] = None
    # 2026-05-25 — LLM call-log subsystem toggle + retention window.
    call_logging_enabled: Optional[bool] = None
    call_log_retention_days: Optional[int] = Field(default=None, ge=1, le=365)


class SettingsTestRequest(BaseModel):
    """One-off test of the currently-configured provider — runs a tiny
    prompt so the user can verify the key + model work."""
    pass


class SettingsTestResponse(BaseModel):
    ok: bool
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# T-004 — Provider healthcheck
# ---------------------------------------------------------------------------

class HealthcheckProbe(BaseModel):
    """One probe result. Keyed by the (provider, model) pair so the UI
    can collapse duplicates — if two stages point at the same model
    they share one probe."""
    provider: str
    model: str
    ok: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    # The stage keys that resolve to this (provider, model) pair —
    # lets the UI render a "used by: preflight_planner, agent_default"
    # subtitle on the result chip.
    stages: list[str] = Field(default_factory=list)


class HealthcheckResponse(BaseModel):
    """Returned by ``POST /settings/healthcheck``.

    ``overall_ok`` is True iff every probe returned ``ok=True``. When
    ``cached`` is True the results are reused from the last on-startup
    probe within the cache TTL — pass ``force=true`` to re-probe.
    """
    overall_ok: bool
    cached: bool = False
    checked_at: str
    probes: list[HealthcheckProbe] = Field(default_factory=list)


class HealthcheckRequest(BaseModel):
    """Body for ``POST /settings/healthcheck``."""
    force: bool = False


# ---------------------------------------------------------------------------
# LLM call log (observability, shipped 2026-05-25)
# ---------------------------------------------------------------------------

class CallLogSummary(BaseModel):
    """One row in the Call log tab's list view. Bodies omitted to keep
    list responses cheap — fetch the detail endpoint for full JSON."""
    call_log_id: int
    correlation_id: Optional[str] = None
    trigger_source: str
    trigger_ref_kind: Optional[str] = None
    trigger_ref_id: Optional[int] = None
    user_id: Optional[int] = None
    provider_config_id: Optional[int] = None
    provider_kind: str
    provider_label: Optional[str] = None
    base_url: str
    model: str
    stage_key: Optional[str] = None
    response_status: Optional[int] = None
    succeeded: bool
    error: Optional[str] = None
    latency_ms: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    started_at: str

    class Config:
        from_attributes = True


class CallLogDetail(CallLogSummary):
    """Full detail — same fields as summary plus the request + response
    bodies (capped at 64KB per side; truncated flags surfaced)."""
    request_method: str
    request_path: str
    request_body: Optional[str] = None
    request_headers: Optional[str] = None
    request_truncated: bool
    response_body: Optional[str] = None
    response_truncated: bool


class CallLogListResponse(BaseModel):
    items: list[CallLogSummary]
    total: int
    next_cursor: Optional[int] = None


class CallLogCorrelationResponse(BaseModel):
    """All log rows sharing one correlation_id, oldest first. Used by
    the UI's 'show siblings' affordance to see the full LLM trace of
    one user-facing operation."""
    correlation_id: str
    items: list[CallLogDetail]


# ---------------------------------------------------------------------------
# Multi-provider config (refactor of T-901+T-902, shipped 2026-05-25)
# ---------------------------------------------------------------------------

class ProviderConfigPayload(BaseModel):
    """Returned by ``GET /settings/providers``. Never carries the raw
    API key — only the ``has_api_key`` flag."""
    provider_config_id: int
    kind: str
    display_name: str
    base_url: Optional[str] = None
    has_api_key: bool
    is_active: bool
    description: Optional[str] = None
    openrouter_referer: Optional[str] = None
    openrouter_app_name: Optional[str] = None
    # Admin-entered per-provider default model. Used by stage routing
    # when a stage row leaves Model blank.
    default_model: str = ""
    # 2026-05-25: single-default flag. Exactly one provider in the
    # system has this True; the stage-routing fallback uses that
    # provider's ``default_model``.
    is_default: bool = False


class ProviderConfigListResponse(BaseModel):
    items: list[ProviderConfigPayload]
    total: int
    kinds: list[str] = Field(default_factory=list)


class ProviderConfigCreate(BaseModel):
    kind: str = Field(..., max_length=40)
    display_name: str = Field(..., min_length=1, max_length=200)
    api_key: str = Field(..., min_length=1)
    # 2026-05-25: per-provider default model is now required at create
    # time so stage routing can fall back to a known value when a
    # stage row leaves Model blank. UI pre-fills from KIND_DEFAULTS
    # the moment the admin picks a kind.
    default_model: str = Field(..., min_length=1, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    openrouter_referer: Optional[str] = Field(default=None, max_length=500)
    openrouter_app_name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    # When True, this provider becomes the system default at create
    # time (any previous default is automatically demoted). The very
    # first provider is auto-promoted regardless so the resolver
    # always has a fallback target.
    is_default: bool = False


class ProviderConfigUpdate(BaseModel):
    """PUT body. ``api_key`` uses the same KEEP sentinel as legacy
    settings — pass ``KEEP_API_KEY`` to leave the stored value alone."""
    kind: Optional[str] = Field(default=None, max_length=40)
    display_name: Optional[str] = Field(default=None, max_length=200)
    api_key: str = Field(default=KEEP_API_KEY)
    # ``None`` = leave alone. Cannot be set to an empty string — the
    # service raises a 400 because a blank default model breaks the
    # stage-routing fallback.
    default_model: Optional[str] = Field(default=None, max_length=200)
    base_url: Optional[str] = Field(default=None, max_length=500)
    openrouter_referer: Optional[str] = Field(default=None, max_length=500)
    openrouter_app_name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    # ``True`` promotes this provider; ``False`` demotes (next active
    # provider is auto-promoted so the system always has a default);
    # ``None`` leaves the flag alone.
    is_default: Optional[bool] = None


class ProviderTestRequest(BaseModel):
    """``POST /settings/providers/{id}/test`` body. ``model`` lets the
    UI test a specific stage-routing model; None uses the provider's
    default for its kind."""
    model: Optional[str] = Field(default=None, max_length=200)


class ProviderTestResponse(BaseModel):
    """Returned by per-provider test. Shows enough detail for a
    diagnostic ('which model did we send', 'how long did it take',
    'what came back') without leaking the API key."""
    provider_config_id: int
    display_name: str
    kind: str
    base_url: Optional[str] = None
    model_used: str
    ok: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    # Echo the model the API responded with — different from
    # ``model_used`` when the provider normalises / routes. OpenRouter
    # often echoes the upstream model name; this is how the admin
    # confirms the request actually reached OpenRouter (not OpenAI
    # via a stale fallback).
    response_model: Optional[str] = None
    # Short preview of the response text (first 80 chars). Helps
    # confirm the round-trip is reaching the intended provider.
    response_preview: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase B1 — Smart-analysis chatbot
# ---------------------------------------------------------------------------

class ChatSessionSummary(BaseModel):
    """Lightweight row for the sessions sidebar."""
    chat_session_id: int
    title: Optional[str] = None
    is_active: bool
    message_count: int
    last_message_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    """One turn in a session — user prompt or assistant pipeline result."""
    chat_message_id: int
    chat_session_id: int
    role: str  # 'user' | 'assistant'
    # Discriminator for the *kind* of assistant turn:
    #   'answer'  - canonical successful query turn (default)
    #   'clarify' - Pre-flight Planner asking the user a follow-up
    # Frontend chooses bubble styling + suppresses chart/SQL panes
    # accordingly. Always 'answer' for user turns by convention.
    kind: str = "answer"
    content: str

    # Assistant-only payload — null for user turns.
    sql: Optional[str] = None
    rewritten_sql: Optional[str] = None
    result_columns: Optional[List[str]] = None
    result_rows: Optional[List[List[Any]]] = None
    chart_config: Optional[ChartConfig] = None
    agent_steps: Optional[List[NlAgentStep]] = None

    # Phase B3 — second LLM pass narrative + follow-up actions.
    insight: Optional[str] = None
    recommendations: Optional[List[str]] = None

    succeeded: bool = True
    error: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    tokens: int = 0
    duration_ms: int = 0
    created_at: datetime


class ChatSessionDetail(BaseModel):
    chat_session_id: int
    title: Optional[str] = None
    company_id: Optional[int] = None
    user_id: Optional[int] = None
    is_active: bool
    rolling_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessage] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    items: List[ChatSessionSummary]
    total: int


class ChatSessionCreateRequest(BaseModel):
    """Optional title; otherwise the first turn auto-derives one."""
    title: Optional[str] = Field(default=None, max_length=200)


class ChatSessionUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class ChatTurnRequest(BaseModel):
    """User prompt for one turn."""
    prompt: str = Field(..., min_length=1, max_length=4000)


class ChatTurnResponse(BaseModel):
    """Both messages produced by a single turn — user echo + assistant
    reply. The frontend appends both to its rendered message list."""
    user_message: ChatMessage
    assistant_message: ChatMessage


# ---------------------------------------------------------------------------
# Eval harness (T-001)
# ---------------------------------------------------------------------------
# Golden test cases for the NL→SQL agent and per-run reports. Detailed
# semantics live in ``kpi_studio.models.KpiEvalCase`` and
# ``kpi_studio.eval.runner``; these are just the wire shapes.


class EvalCaseCreate(BaseModel):
    """POST body for ``POST /eval/cases``."""
    name: str = Field(..., min_length=1, max_length=200)
    prompt: str = Field(..., min_length=1)
    expected_tables: Optional[list[str]] = None
    expected_columns: Optional[list[str]] = None
    expected_row_count_min: Optional[int] = Field(None, ge=0)
    expected_row_count_max: Optional[int] = Field(None, ge=0)
    golden_sql: Optional[str] = None
    strict_tables: bool = False
    tags: Optional[list[str]] = None
    pinned_snapshot_id: Optional[int] = None


class EvalCaseUpdate(BaseModel):
    """PUT body for ``PUT /eval/cases/{id}``. All fields optional."""
    name: Optional[str] = None
    prompt: Optional[str] = None
    expected_tables: Optional[list[str]] = None
    expected_columns: Optional[list[str]] = None
    expected_row_count_min: Optional[int] = None
    expected_row_count_max: Optional[int] = None
    golden_sql: Optional[str] = None
    strict_tables: Optional[bool] = None
    tags: Optional[list[str]] = None
    is_active: Optional[bool] = None
    pinned_snapshot_id: Optional[int] = None


class EvalCasePayload(BaseModel):
    """Returned by case GETs."""
    case_id: int
    name: str
    prompt: str
    expected_tables: Optional[list[str]] = None
    expected_columns: Optional[list[str]] = None
    expected_row_count_min: Optional[int] = None
    expected_row_count_max: Optional[int] = None
    golden_sql: Optional[str] = None
    strict_tables: bool
    tags: Optional[list[str]] = None
    is_active: bool
    last_pass_at: Optional[str] = None
    last_fail_reason: Optional[str] = None
    pinned_snapshot_id: Optional[int] = None

    class Config:
        from_attributes = True


class EvalCaseListResponse(BaseModel):
    items: list[EvalCasePayload]
    total: int


class EvalRunRequest(BaseModel):
    """POST body for ``POST /eval/runs``. All fields optional."""
    tags: Optional[list[str]] = None
    case_ids: Optional[list[int]] = None
    against_snapshot_id: Optional[int] = None


class EvalCaseResultPayload(BaseModel):
    """Per-case outcome inside a run, returned by ``GET /eval/runs/{id}``."""
    result_id: int
    case_id: int
    status: str
    produced_sql: Optional[str] = None
    produced_row_count: Optional[int] = None
    tables_referenced: Optional[list[str]] = None
    columns_referenced: Optional[list[str]] = None
    failure_reasons: Optional[list[str]] = None
    failure_detail: Optional[dict] = None
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    nl_run_id: Optional[int] = None

    class Config:
        from_attributes = True


class EvalRunPayload(BaseModel):
    """Run-level summary. Returned by ``GET /eval/runs`` (list) and
    ``GET /eval/runs/{id}`` (detail, with embedded ``results``)."""
    eval_run_id: int
    started_at: str
    finished_at: Optional[str] = None
    triggered_by: str
    tags_filter: Optional[list[str]] = None
    snapshot_id: Optional[int] = None
    prompt_version: Optional[str] = None
    cases_total: int
    cases_passed: int
    cases_failed: int
    cases_errored: int
    cases_skipped: int
    pass_rate: float
    summary_json: Optional[dict] = None
    results: Optional[list[EvalCaseResultPayload]] = None

    class Config:
        from_attributes = True


class EvalRunListResponse(BaseModel):
    items: list[EvalRunPayload]
    total: int


# ---------------------------------------------------------------------------
# Scheduler (T-003)
# ---------------------------------------------------------------------------
# Wire shapes for /jobs/* admin endpoints. Jobs themselves are declared
# in code (services.scheduler.register), so there's no CRUD — just
# read-only listing + a Run-now trigger.


class JobTriggerInfo(BaseModel):
    """Human-readable summary of the APScheduler trigger.

    The raw trigger types differ between interval / cron; this is a
    flattened representation the admin UI can render uniformly. The
    ``next_fire_at`` field is best-effort (only set when the scheduler
    is running and the job is attached)."""
    kind: str  # "interval" | "cron" | "unknown"
    interval_seconds: Optional[int] = None
    cron_expression: Optional[str] = None
    next_fire_at: Optional[str] = None


class ScheduledJobPayload(BaseModel):
    """One registered job. Returned by ``GET /jobs``."""
    name: str
    description: str
    enabled: bool
    trigger: JobTriggerInfo
    # Latest run summary — populated by the API handler via a small
    # JOIN against KpiScheduledJobRun so the list page doesn't N+1
    # query for last-run metadata.
    last_run_id: Optional[int] = None
    last_run_status: Optional[str] = None
    last_run_started_at: Optional[str] = None
    last_run_finished_at: Optional[str] = None
    last_run_duration_ms: Optional[int] = None


class ScheduledJobListResponse(BaseModel):
    items: list[ScheduledJobPayload]
    total: int
    scheduler_active: bool


class ScheduledJobRunPayload(BaseModel):
    """One execution row from kpi_scheduled_job_run."""
    run_id: int
    job_name: str
    trigger_source: str
    triggered_by_user_id: Optional[int] = None
    status: str
    error: Optional[str] = None
    items_processed: Optional[int] = None
    duration_ms: Optional[int] = None
    started_at: str
    finished_at: Optional[str] = None
    detail_json: Optional[dict] = None

    class Config:
        from_attributes = True


class ScheduledJobRunListResponse(BaseModel):
    items: list[ScheduledJobRunPayload]
    total: int


class ScheduledJobTriggerResponse(BaseModel):
    """Returned by ``POST /jobs/{name}/trigger``."""
    run_id: int
    job_name: str
    status: str
