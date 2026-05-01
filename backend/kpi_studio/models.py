"""SQLAlchemy models owned by kpi_studio.

All tables are prefixed (default ``kpi_``) and live alongside host tables
in the metadata DB. The package's Alembic env imports this module so its
migration autogenerate sees these tables.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KpiBase(DeclarativeBase):
    """Separate declarative base so kpi_studio metadata doesn't leak into
    the host's Base.metadata. The host's Alembic env doesn't see these,
    and the package's Alembic env doesn't see the host's models."""
    pass


# ---------------------------------------------------------------------------
# Phase 1
# ---------------------------------------------------------------------------

class KpiSchemaSnapshot(KpiBase):
    """Cached reflection of a target schema.

    A snapshot is one *version* of the schema as introspected at a point
    in time. Endpoints serve the latest snapshot per ``database_key``;
    older rows are kept as an audit trail.
    """
    __tablename__ = "kpi_schema_snapshot"

    snapshot_id = Column(Integer, primary_key=True, autoincrement=True)
    database_key = Column(String(64), nullable=False, default="primary")
    payload = Column(JSON, nullable=False)
    table_count = Column(Integer, nullable=False, default=0)
    relationship_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_kpi_schema_snapshot_current", "database_key", "is_current"),
    )


# ---------------------------------------------------------------------------
# Phase A1 — KPI authoring
# ---------------------------------------------------------------------------

class KpiDefinition(KpiBase):
    """Top-level KPI record. Holds identity + ownership.

    Versioned mutable bits (query, chart config) live on KpiVersion so
    edits never clobber a card pinned by a published dashboard.
    """
    __tablename__ = "kpi_definition"

    kpi_id = Column(Integer, primary_key=True, autoincrement=True)

    # Tenant + ownership. ``company_id`` is set from the host's tenant
    # resolver at create time and never mutated. ``owner_user_id`` is the
    # original author; later phases may add transfer.
    company_id = Column(Integer, nullable=True)
    owner_user_id = Column(Integer, nullable=True)

    name = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)

    # Pointer to the latest published version. NULL during the brief
    # window between definition insert and first version insert.
    current_version_id = Column(
        Integer,
        ForeignKey("kpi_version.version_id", use_alter=True, name="fk_kpi_def_current_version"),
        nullable=True,
    )

    # Soft delete. UI hides ``is_active=False``; dashboards that pin a
    # version of a deleted KPI render a "deleted" placeholder.
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(Integer, nullable=True)

    versions = relationship(
        "KpiVersion",
        back_populates="definition",
        foreign_keys="KpiVersion.kpi_id",
        cascade="all, delete-orphan",
        order_by="KpiVersion.version_no.desc()",
    )

    __table_args__ = (
        Index("ix_kpi_def_company_active", "company_id", "is_active"),
        Index("ix_kpi_def_owner", "owner_user_id"),
    )


class KpiVersion(KpiBase):
    """Immutable snapshot of a KPI's authoring state.

    Editing a KPI inserts a new row + bumps ``KpiDefinition.current_version_id``.
    Dashboards pin a specific ``version_id`` so an in-flight edit never
    breaks a published board.
    """
    __tablename__ = "kpi_version"

    version_id = Column(Integer, primary_key=True, autoincrement=True)
    kpi_id = Column(
        Integer,
        ForeignKey("kpi_definition.kpi_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no = Column(Integer, nullable=False, default=1)

    # The SQL the executor will run. Always SELECT-only — enforced at the
    # API edge by sql_safety.validate_select_query.
    query_text = Column(Text, nullable=False)

    # Which DB this query targets. ``"primary"`` for now; future-proofing
    # for multi-DB introspection.
    database_key = Column(String(64), nullable=False, default="primary")

    # Chart config: { "type": "scorecard"|"bar"|"line"|"pie"|"table",
    #                 "x": "...", "y": "...", ... }
    chart_config = Column(JSON, nullable=False, default=dict)

    # Author-time params (Phase A1 doesn't bind them yet, but the column
    # exists so we don't migrate again later).
    params_schema = Column(JSON, nullable=True)

    # Optional name of the date/datetime column the time-period selector
    # filters on. Stored as plain text — referential by convention to a
    # column in ``query_text``. ``None`` means the KPI ignores the global
    # time selector entirely. Phase A5.
    time_column = Column(String(100), nullable=True)

    # Phase C — Smart Builder source-of-truth. When non-null the KPI
    # was authored via the drag-into-wells editor; ``query_text`` is a
    # *derived* value that's recompiled from this spec on every save,
    # so editing always round-trips losslessly. ``None`` means the KPI
    # is in raw-SQL mode (the legacy authoring path) — query_text is
    # the source of truth.
    builder_spec = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)

    definition = relationship(
        "KpiDefinition",
        back_populates="versions",
        foreign_keys=[kpi_id],
    )

    __table_args__ = (
        Index("ix_kpi_version_kpi_no", "kpi_id", "version_no"),
    )


class KpiQueryRun(KpiBase):
    """Audit log of every executed query.

    Includes preview runs (no version_id), saved-KPI runs, and chat
    pipeline runs (Phase B). Always written, even on failure.
    """
    __tablename__ = "kpi_query_run"

    run_id = Column(Integer, primary_key=True, autoincrement=True)

    # NULL for preview runs (KPI not saved yet) and chat-pipeline runs.
    kpi_version_id = Column(
        Integer,
        ForeignKey("kpi_version.version_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Tenant + actor.
    company_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)

    # Where this run came from — enables filtering audit log by surface.
    # One of: ``"preview"``, ``"kpi_run"``, ``"chat"``.
    source = Column(String(20), nullable=False, default="preview")

    # The exact SQL submitted to the executor (post-validator). Stored so
    # an auditor can replay the query that ran.
    query_text = Column(Text, nullable=False)

    # Outcome.
    succeeded = Column(Boolean, nullable=False, default=True)
    error = Column(Text, nullable=True)
    row_count = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    truncated = Column(Boolean, nullable=False, default=False)

    started_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_kpi_run_company_started", "company_id", "started_at"),
        Index("ix_kpi_run_user_started", "user_id", "started_at"),
        Index("ix_kpi_run_version", "kpi_version_id"),
    )


# ---------------------------------------------------------------------------
# Phase A2 — Dashboards
# ---------------------------------------------------------------------------

# Discrete dashboard scopes. ``user`` = private (owner-only), ``company`` =
# shared with everyone in the same tenant. Storing as string keeps the DB
# self-describing; an enum table would be over-engineering here.
DASHBOARD_SCOPE_USER = "user"
DASHBOARD_SCOPE_COMPANY = "company"

# Discrete card sizes used by the grid layout. Each maps to a span on the
# CSS grid: sm=1, md=2, lg=3, wide=4 columns. Limiting to four options
# keeps the editor UX simple and avoids the x/y/w/h coordinate maths.
CARD_SIZES = ("sm", "md", "lg", "wide")


class KpiDashboard(KpiBase):
    """A KPI dashboard — a named collection of KPI cards.

    ``scope`` controls visibility:
      * ``user``    → only ``owner_user_id`` sees it
      * ``company`` → everyone with the same ``company_id`` sees it
    SuperAdmin always sees everything.
    """
    __tablename__ = "kpi_dashboard"

    dashboard_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(String(1000), nullable=True)

    scope = Column(String(20), nullable=False, default=DASHBOARD_SCOPE_USER)
    owner_user_id = Column(Integer, nullable=True)
    company_id = Column(Integer, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(Integer, nullable=True)

    items = relationship(
        "KpiDashboardItem",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        order_by="KpiDashboardItem.position",
    )
    assignments = relationship(
        "KpiDashboardAssignment",
        back_populates="dashboard",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_kpi_dashboard_company_scope", "company_id", "scope"),
        Index("ix_kpi_dashboard_owner", "owner_user_id"),
    )


class KpiDashboardAssignment(KpiBase):
    """Per-role or per-user grant on a dashboard.

    Adds a third visibility path on top of the existing ``scope`` field:
    a user can see a dashboard if they own it, if it's company-scoped and
    in their company, OR if there's a matching assignment row.

    Exactly one of ``role_id`` / ``user_id`` is set per row — enforced at
    the API edge (cross-dialect CHECK constraints are messy). Two rows
    on the same dashboard can grant to a role *and* a specific user, or
    multiple users, etc.

    No FKs to the host's RoleMaster / UserMaster — keeps the package
    portable; the columns are referential by convention only.
    """
    __tablename__ = "kpi_dashboard_assignment"

    assignment_id = Column(Integer, primary_key=True, autoincrement=True)
    dashboard_id = Column(
        Integer,
        ForeignKey("kpi_dashboard.dashboard_id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)

    granted_by = Column(Integer, nullable=True)
    granted_at = Column(DateTime, nullable=False, default=_utcnow)

    dashboard = relationship("KpiDashboard", back_populates="assignments")

    __table_args__ = (
        Index("ix_kpi_dash_assign_dashboard", "dashboard_id"),
        Index("ix_kpi_dash_assign_role", "role_id"),
        Index("ix_kpi_dash_assign_user", "user_id"),
    )


class KpiDashboardItem(KpiBase):
    """One KPI placed on a dashboard.

    Always references ``kpi_id`` (not ``kpi_version_id``) — per the design
    decision that "Save as KPI" / dashboard cards re-execute the *current*
    version live every render. If the underlying KPI is soft-deleted, the
    card renders a placeholder.
    """
    __tablename__ = "kpi_dashboard_item"

    item_id = Column(Integer, primary_key=True, autoincrement=True)
    dashboard_id = Column(
        Integer,
        ForeignKey("kpi_dashboard.dashboard_id", ondelete="CASCADE"),
        nullable=False,
    )
    kpi_id = Column(
        Integer,
        ForeignKey("kpi_definition.kpi_id", ondelete="CASCADE"),
        nullable=False,
    )

    # 0-based ordinal — drag-drop renumbers all items in a single PUT.
    # Kept after Phase D as a backward-compat read path; new layouts
    # rely on ``grid_*`` coordinates instead.
    position = Column(Integer, nullable=False, default=0)
    # One of CARD_SIZES. Still useful as a coarse "preset" the editor
    # can offer; the real authoritative placement is ``grid_*``.
    size_class = Column(String(8), nullable=False, default="md")

    # Phase D — Power BI–style free-form grid coordinates. Each tile
    # claims a rectangle on a 12-column grid; ``grid_y`` is row and
    # ``grid_h`` is height in row units (default row height = 80px).
    # Nullable so existing rows survive the migration; the API
    # backfills sensible values from ``position`` + ``size_class`` on
    # first read.
    grid_x = Column(Integer, nullable=True)
    grid_y = Column(Integer, nullable=True)
    grid_w = Column(Integer, nullable=True)
    grid_h = Column(Integer, nullable=True)

    # Lets a user rename a KPI as it appears on this specific dashboard
    # without touching the underlying KpiDefinition.
    title_override = Column(String(200), nullable=True)

    # Phase J.2 — per-dashboard-item visual + filter overrides set by the
    # AI Polish action. All NULL means "no override" — the card renders
    # exactly as the KPI was authored.
    icon = Column(String(64), nullable=True)
    animation_in = Column(String(16), nullable=True)
    animation_out = Column(String(16), nullable=True)
    # Bar / line chart axis titles. Override the KPI chart_config's
    # x_label / y_label without touching the KPI definition.
    x_label = Column(String(120), nullable=True)
    y_label = Column(String(120), nullable=True)
    # List of BuilderFilter dicts. Merged with the KPI's own filters at
    # execute time; lets the same KPI appear on two boards with
    # different slices without forking the definition.
    filters_json = Column(JSON, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)

    dashboard = relationship("KpiDashboard", back_populates="items")

    __table_args__ = (
        Index("ix_kpi_dashboard_item_dash_pos", "dashboard_id", "position"),
    )


class KpiNlRun(KpiBase):
    """Audit log of NL→SQL agent runs (Phase A7).

    One row per agent invocation. ``steps`` is the full timeline as
    JSON, suitable for replay or debugging. Same table will record
    Phase B chat-pipeline turns; the ``surface`` column distinguishes
    "editor" generations from "chat" turns.
    """
    __tablename__ = "kpi_nl_run"

    nl_run_id = Column(Integer, primary_key=True, autoincrement=True)

    # Tenant + actor.
    company_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)

    # ``editor`` for "Generate from prompt" in the KPI editor;
    # ``chat`` for Phase B turns. Free-form so future surfaces can extend.
    surface = Column(String(20), nullable=False, default="editor")

    prompt = Column(Text, nullable=False)
    final_sql = Column(Text, nullable=True)
    explanation = Column(Text, nullable=True)

    succeeded = Column(Boolean, nullable=False, default=True)
    error = Column(String(200), nullable=True)

    provider = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    iterations = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)

    # Full step timeline ([{type, tool, args, output, error, latency_ms}, …]).
    steps = Column(JSON, nullable=True)

    started_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_kpi_nl_run_company_started", "company_id", "started_at"),
        Index("ix_kpi_nl_run_user_started", "user_id", "started_at"),
    )


class KpiChatSession(KpiBase):
    """One conversational thread between a user and the smart-analysis
    agent. Owned by a single user; not shared.

    ``rolling_summary`` is reserved for Phase B3 — the chatbot will
    compress older history into a short summary every N Q&A pairs to
    keep the context window flat.
    """
    __tablename__ = "kpi_chat_session"

    chat_session_id = Column(Integer, primary_key=True, autoincrement=True)

    company_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)

    # User-editable label; auto-derived from the first prompt when blank.
    title = Column(String(200), nullable=True)

    # Phase B3 — single-paragraph LLM summary of older messages, used in
    # place of the raw history once a session grows beyond the trigger.
    rolling_summary = Column(Text, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    messages = relationship(
        "KpiChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="KpiChatMessage.created_at.asc()",
    )

    __table_args__ = (
        Index("ix_kpi_chat_session_user_updated", "user_id", "updated_at"),
        Index("ix_kpi_chat_session_active", "user_id", "is_active"),
    )


class KpiChatMessage(KpiBase):
    """One turn in a chat session.

    User turns carry only ``content`` (the prompt). Assistant turns
    carry the full pipeline result: explanation in ``content``, the SQL
    in ``sql``, the safe-rewritten variant in ``rewritten_sql``,
    execution columns/rows, agent step timeline, plus token/duration
    bookkeeping.
    """
    __tablename__ = "kpi_chat_message"

    chat_message_id = Column(Integer, primary_key=True, autoincrement=True)
    chat_session_id = Column(
        Integer,
        ForeignKey("kpi_chat_session.chat_session_id", ondelete="CASCADE"),
        nullable=False,
    )

    role = Column(String(20), nullable=False)  # 'user' | 'assistant'
    content = Column(Text, nullable=False, default="")

    # Assistant-only fields. Null for user turns.
    sql = Column(Text, nullable=True)
    rewritten_sql = Column(Text, nullable=True)
    result_columns = Column(JSON, nullable=True)
    result_rows = Column(JSON, nullable=True)
    chart_config = Column(JSON, nullable=True)
    agent_steps = Column(JSON, nullable=True)

    # Phase B3 — insight + recommendations from a second LLM pass that
    # reads the executed result and produces a short narrative + a list
    # of actionable follow-ups. Both nullable: a turn can succeed with
    # data but the insight pass can fail / be disabled — we degrade
    # silently rather than fail the whole turn.
    insight = Column(Text, nullable=True)
    recommendations = Column(JSON, nullable=True)

    succeeded = Column(Boolean, nullable=False, default=True)
    error = Column(String(500), nullable=True)

    provider = Column(String(50), nullable=True)
    model = Column(String(100), nullable=True)
    tokens = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    session = relationship("KpiChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_kpi_chat_message_session", "chat_session_id", "created_at"),
    )


class KpiTableRelationship(KpiBase):
    """A directional join edge between two tables in the host schema.

    Phase F — Data Modeling. Powers the Power BI–style "drag a related
    column in" experience: the spec compiler walks these edges to
    auto-emit ``LEFT JOIN`` clauses, so users never write SQL for the
    common cases.

    ``from_*`` is the foreign-key holder (the "many" side of a
    many-to-one); ``to_*`` is the parent (the "one" side). Direction
    matters because LEFT JOIN preserves rows from the FROM side; the
    compiler always navigates from a fact table outward.
    """
    __tablename__ = "kpi_table_relationship"

    relationship_id = Column(Integer, primary_key=True, autoincrement=True)

    # Per-tenant scoping. NULL = applies to every tenant (the typical
    # case for FK-derived relationships, since the schema is shared).
    company_id = Column(Integer, nullable=True)

    # FK side (e.g. enquiries.customer_id).
    from_schema = Column(String(64), nullable=True)
    from_table = Column(String(128), nullable=False)
    from_column = Column(String(128), nullable=False)
    # Referenced side (e.g. customers.id).
    to_schema = Column(String(64), nullable=True)
    to_table = Column(String(128), nullable=False)
    to_column = Column(String(128), nullable=False)

    # ``many_to_one`` is the default for a typical FK; ``one_to_one``
    # for unique FKs; ``one_to_many`` is the inverse (rarely set
    # explicitly — the compiler can navigate edges in either direction).
    cardinality = Column(String(20), nullable=False, default="many_to_one")

    # Provenance: ``auto`` (introspector-seeded from DB FKs) or
    # ``manual`` (user-defined). Auto rows are replaced on re-seed;
    # manual rows are preserved.
    source = Column(String(20), nullable=False, default="auto")

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_kpi_relationship_from", "from_table", "from_column"),
        Index("ix_kpi_relationship_to", "to_table", "to_column"),
        Index("ix_kpi_relationship_company", "company_id", "is_active"),
    )


class KpiSettings(KpiBase):
    """Runtime-editable LLM + agent settings.

    Single global row (singleton). When present, takes precedence over
    the ``KPI_*`` env vars so a SuperAdmin can flip provider / key /
    budget without an SSH-and-restart cycle. Empty / unset DB columns
    fall back to env, then to compile-time defaults.

    The API key is **write-only**: ``GET /settings`` never returns the
    raw value — only a ``has_api_key`` boolean. Updates accept the key
    via PUT body; sending an empty string clears it.
    """
    __tablename__ = "kpi_settings"

    settings_id = Column(Integer, primary_key=True, autoincrement=True)

    # LLM provider selection. Currently one of:
    # ``openai`` | ``cerebras`` | ``ollama_cloud``  (OpenAI-compat impl)
    # Empty string = use env var KPI_LLM_PROVIDER instead.
    llm_provider = Column(String(40), nullable=True)

    # OpenAI-family creds. ``openai_api_key`` is plaintext; protect via
    # DB-level access control. Future hardening: encrypt at rest with a
    # ``KPI_SETTINGS_KEY`` master env var (Fernet).
    openai_api_key = Column(Text, nullable=True)
    openai_model = Column(String(100), nullable=True)
    openai_base_url = Column(String(500), nullable=True)

    # Agent caps. Null = use env or defaults.
    token_budget = Column(Integer, nullable=True)
    max_iterations = Column(Integer, nullable=True)
    max_tokens_per_call = Column(Integer, nullable=True)

    # System Knowledge Hub — admin-curated domain context appended to the
    # agent's system prompt on every turn. Tells the LLM about the
    # business model: what a "parent code" means, who the "owner" is,
    # how location mapping works, the lifecycle of an enquiry / quotation,
    # etc. Plain text (markdown-friendly). Null = skip the extras block.
    domain_knowledge = Column(Text, nullable=True)

    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(Integer, nullable=True)


__all__ = [
    "KpiBase",
    "KpiSchemaSnapshot",
    "KpiDefinition",
    "KpiVersion",
    "KpiQueryRun",
    "KpiDashboard",
    "KpiDashboardItem",
    "KpiDashboardAssignment",
    "KpiNlRun",
    "KpiChatSession",
    "KpiChatMessage",
    "KpiSettings",
    "KpiTableRelationship",
    "DASHBOARD_SCOPE_USER",
    "DASHBOARD_SCOPE_COMPANY",
    "CARD_SIZES",
]
