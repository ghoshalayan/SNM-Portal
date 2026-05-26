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

    # ---- Knowledge fingerprint (T-002) -----------------------------------
    # All four are nullable / soft-defaulted so existing rows aren't
    # broken; the writer stamps them on every new insert via
    # ``services.knowledge_versions.current()``. Pinning lets us
    # correlate a quality regression with the exact prompt / glossary /
    # exemplar / schema state that produced it — invaluable when
    # something starts drifting after a deploy.
    prompt_version = Column(String(20), nullable=True)
    glossary_version = Column(String(40), nullable=True)
    schema_snapshot_id = Column(
        Integer,
        ForeignKey("kpi_schema_snapshot.snapshot_id", ondelete="SET NULL"),
        nullable=True,
    )
    exemplar_set_hash = Column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_kpi_nl_run_company_started", "company_id", "started_at"),
        Index("ix_kpi_nl_run_user_started", "user_id", "started_at"),
        Index("ix_kpi_nl_run_prompt_version", "prompt_version"),
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

    # Discriminator for the *kind* of assistant turn (always 'answer'
    # for user turns by convention):
    #   - 'answer'  : canonical successful query turn (default for all
    #                 pre-existing data + the happy path).
    #   - 'clarify' : Pre-flight Planner couldn't disambiguate and is
    #                 asking the user a follow-up question. ``content``
    #                 holds the question; no SQL / chart / insight.
    # Future variants ('reject', 'plan', etc.) reuse this column.
    kind = Column(String(20), nullable=False, default="answer")

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

    # ---- Knowledge fingerprint (T-002) -----------------------------------
    # Same shape as KpiNlRun — stamp the prompt / glossary / exemplar /
    # schema-snapshot identity of the run that produced this message so
    # historical turns can be correlated with the agent config in force
    # at the time. Stamped only on assistant turns (user turns leave
    # them null).
    prompt_version = Column(String(20), nullable=True)
    glossary_version = Column(String(40), nullable=True)
    schema_snapshot_id = Column(
        Integer,
        ForeignKey("kpi_schema_snapshot.snapshot_id", ondelete="SET NULL"),
        nullable=True,
    )
    exemplar_set_hash = Column(String(64), nullable=True)

    session = relationship("KpiChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_kpi_chat_message_session", "chat_session_id", "created_at"),
        Index("ix_kpi_chat_message_prompt_version", "prompt_version"),
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

    # ----- Pre-flight Planner / Resolver knobs -----
    # All nullable — Python-side resolution in settings_service supplies
    # sensible defaults so a fresh row works without admin intervention.
    #
    # ``preflight_enabled``    — kill switch for the entire preflight loop
    # ``preflight_max_rounds`` — Planner ↔ Resolver round cap (default 5)
    # ``preflight_user_escalations`` — consecutive ``ask_user`` turns we
    #                            allow before forcing ``ready`` (default 2)
    preflight_enabled = Column(Boolean, nullable=True)
    preflight_max_rounds = Column(Integer, nullable=True)
    preflight_user_escalations = Column(Integer, nullable=True)

    # ---- T-901: OpenRouter extras ----------------------------------------
    # Two HTTP headers OpenRouter recommends for routing fairness +
    # analytics. Only sent when ``llm_provider == 'openrouter'``. Both
    # nullable; safe to leave blank.
    openrouter_referer = Column(String(500), nullable=True)
    openrouter_app_name = Column(String(200), nullable=True)

    # ---- T-902: Per-stage model routing ----------------------------------
    # JSON map of {stage_key: model_string}. Stages declared in
    # ``kpi_studio.stages``. When a stage is missing, the resolver falls
    # back to ``default_stage_model``; when that's also blank it falls
    # back to ``openai_model``. All three null → factory default.
    #
    # Example payload:
    #   {
    #     "preflight_planner":  "anthropic/claude-3.5-sonnet",
    #     "agent_default":      "anthropic/claude-3-opus",
    #     "insight_generator":  "openai/gpt-4o-mini"
    #   }
    stage_models = Column(JSON, nullable=True)
    default_stage_model = Column(String(200), nullable=True)

    # 2026-05-25 — kill switch for automatic LLM probes (T-004).
    # When False:
    #   * PUT /settings does NOT run the healthcheck — saves commit
    #     unconditionally, no rollback. This is the fix for "I keep
    #     getting healthcheck_failed and can't save".
    #   * The weekly ``provider_healthcheck`` scheduled job becomes a no-op.
    #   * The manual "Run health check" button still works — explicit
    #     user click = explicit cost choice.
    # Nullable so existing rows default to "enabled" via the resolver;
    # admins flip to False via the Health tab when probe billing is a
    # concern (OpenRouter charges per request even for 1-token probes).
    healthcheck_auto_enabled = Column(Boolean, nullable=True)

    # 2026-05-25 — LLM call-log observability switch.
    # When True (default), every outbound LLM HTTP call is recorded
    # to kpi_llm_call_log (request body, response body, latency, etc.).
    # API keys are masked before persist. Toggle off if storage cost
    # is a concern (call_log_retention_days handles the recurring side
    # via a scheduled prune).
    call_logging_enabled = Column(Boolean, nullable=True)
    # Days of call-log history to keep. The scheduled prune job
    # deletes rows older than this. Default 7. Null = use default.
    call_log_retention_days = Column(Integer, nullable=True)

    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(Integer, nullable=True)


# ---------------------------------------------------------------------------
# Multi-provider config (T-901+T-902 refactor, shipped 2026-05-25)
# ---------------------------------------------------------------------------
# Each row is one configured LLM provider — an admin can have several
# coexist (e.g. one OpenRouter for production, one Cerebras for cheap
# utility calls, one OpenAI for parity testing). Stage routing in
# ``KpiSettings.stage_models`` then picks which config_id to use per
# pipeline stage. The single-provider columns on KpiSettings stay as
# the legacy fallback so unmigrated stages keep working.

# Allowed provider ``kind`` values. Drives the protocol shim selection
# in ``provider_config_service``.
PROVIDER_KINDS = ("openai", "openrouter", "cerebras", "ollama_cloud", "azure_openai")


class KpiLlmProviderConfig(KpiBase):
    """One configured LLM provider.

    Multiple rows are expected. ``kind`` picks the protocol shim;
    ``display_name`` is the admin-set label shown in the stage-routing
    dropdown and the providers tab card. ``api_key`` is plaintext —
    same caveat as the legacy ``KpiSettings.openai_api_key`` column;
    encrypt-at-rest follow-up tracked separately.
    """
    __tablename__ = "kpi_llm_provider_config"

    provider_config_id = Column(Integer, primary_key=True, autoincrement=True)

    # ``openai`` | ``openrouter`` | ``cerebras`` | ``ollama_cloud`` |
    # ``azure_openai``. Validated server-side against PROVIDER_KINDS.
    kind = Column(String(40), nullable=False)

    # Admin-set label. Must be unique per company at the API edge.
    # Examples: "Production OpenRouter", "Cerebras (cheap utility)",
    # "OpenAI parity". Shown verbatim in the stage-routing dropdown.
    display_name = Column(String(200), nullable=False)

    # Plaintext API key. Plumbed write-only via the UI (KEEP sentinel on
    # update; GET returns has_api_key boolean only).
    api_key = Column(Text, nullable=False)

    # Optional base URL override. NULL = use the factory default for the
    # provider kind (e.g. https://api.openai.com/v1 for openai).
    base_url = Column(String(500), nullable=True)

    # OpenRouter-only extras — sent as HTTP headers when the kind is
    # ``openrouter``; ignored otherwise. Stored on every row anyway so
    # switching a row's kind doesn't drop them silently.
    openrouter_referer = Column(String(500), nullable=True)
    openrouter_app_name = Column(String(200), nullable=True)

    # Soft delete. ``is_active=False`` removes the provider from
    # stage-routing dropdowns + healthcheck enumeration but preserves
    # history of which stages it was used by.
    is_active = Column(Boolean, nullable=False, default=True)

    # 2026-05-25: admin-entered default model string for this provider.
    # Required at create time (UI pre-fills from KIND_DEFAULTS when the
    # kind is picked, but the admin can edit before saving). Used by
    # the resolver when a stage row is routed to this provider but
    # leaves the per-stage Model field blank.
    default_model = Column(String(200), nullable=True)

    # 2026-05-25: single-default invariant. Exactly one provider config
    # has is_default=True at any time. Stage routing falls back to this
    # provider's ``default_model`` when a stage has no per-stage
    # override AND ``KpiSettings.default_stage_model`` is blank.
    # Service layer enforces "set one True → unset all others".
    is_default = Column(Boolean, nullable=False, default=False)

    # Free text. Future use: rate-limit notes, who owns the key, etc.
    description = Column(String(500), nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_kpi_provider_config_active", "is_active"),
        Index("ix_kpi_provider_config_kind", "kind"),
        Index("ix_kpi_provider_config_default", "is_default"),
    )


# ---------------------------------------------------------------------------
# LLM call log (observability, shipped 2026-05-25)
# ---------------------------------------------------------------------------
# One row per outbound LLM HTTP call. Captures the request body, the
# response body, the model + provider + base URL, and a correlation_id
# that groups all calls fired during one user-facing operation (chat
# turn, /nl/generate run, eval case, healthcheck pass, etc.).
#
# Authorization headers are masked before persist by ``call_logger``.
# Bodies are capped at 64 KB per side; ``request_truncated`` /
# ``response_truncated`` flag rows that lost detail.

# Allowed trigger_source values. Free-form on the column but enforced
# by call_logger's call sites — surfacing a typo at code-review time
# beats a typo silently breaking the admin UI filter.
CALL_LOG_SOURCES = (
    "chat",                 # chat_service.run_turn
    "nl_generate",          # /nl/generate endpoint
    "eval",                 # eval runner
    "healthcheck_auto",     # scheduled provider_healthcheck job
    "healthcheck_manual",   # admin clicked "Run health check"
    "provider_test",        # admin clicked "Test connection" on a card
    "settings_test",        # legacy /settings/test endpoint
    "unknown",              # default when caller forgot to set
)


class KpiLlmCallLog(KpiBase):
    """One LLM HTTP round-trip. Always inserted, success or failure."""
    __tablename__ = "kpi_llm_call_log"

    call_log_id = Column(Integer, primary_key=True, autoincrement=True)

    # Correlation key — all calls within one user-facing operation
    # share this. UUID4 hex (32 chars); ``None`` when nothing set the
    # context (background job, direct service call).
    correlation_id = Column(String(40), nullable=True)

    # See CALL_LOG_SOURCES.
    trigger_source = Column(String(40), nullable=False, default="unknown")

    # Optional pointer back to the higher-level row this call belongs
    # to. trigger_ref_kind names the table (e.g. "kpi_chat_message"),
    # trigger_ref_id is the PK in that table. Both null when the source
    # is something without a parent row (e.g. provider_test).
    trigger_ref_kind = Column(String(40), nullable=True)
    trigger_ref_id = Column(Integer, nullable=True)

    # Tenant + actor (when known).
    company_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)

    # Provider identity at the time of the call. provider_config_id
    # is nullable because env-bootstrapped providers don't have a row
    # in kpi_llm_provider_config.
    provider_config_id = Column(
        Integer,
        ForeignKey("kpi_llm_provider_config.provider_config_id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_kind = Column(String(40), nullable=False)
    provider_label = Column(String(200), nullable=True)
    base_url = Column(String(500), nullable=False)
    model = Column(String(200), nullable=False)

    # Pipeline stage that asked for this call (when applicable). One
    # of the keys from kpi_studio.stages. Null for healthcheck probes
    # and provider tests.
    stage_key = Column(String(40), nullable=True)

    # Request shape. Always POST today; we record the method + path
    # anyway so future endpoints (embeddings, etc.) classify cleanly.
    request_method = Column(String(10), nullable=False, default="POST")
    request_path = Column(String(200), nullable=False)
    # JSON string (not JSON column — we want to render exactly what
    # was sent, byte-for-byte, including the order of keys). Capped
    # at 64 KB; request_truncated flips when we cropped.
    request_body = Column(Text, nullable=True)
    request_headers = Column(Text, nullable=True)   # masked, JSON string
    request_truncated = Column(Boolean, nullable=False, default=False)

    # Response. response_status is the HTTP code; response_body is
    # the raw text (parsed-or-not JSON). Same 64 KB cap.
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    response_truncated = Column(Boolean, nullable=False, default=False)

    # Outcome.
    succeeded = Column(Boolean, nullable=False, default=False)
    error = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=False, default=0)

    # Token bookkeeping (when the response carried it). Most OpenAI-
    # compatible providers return a ``usage`` block; we mine it.
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    started_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_kpi_llm_call_log_started", "started_at"),
        Index("ix_kpi_llm_call_log_corr", "correlation_id"),
        Index("ix_kpi_llm_call_log_provider", "provider_config_id", "started_at"),
        Index("ix_kpi_llm_call_log_source", "trigger_source", "started_at"),
    )


# ---------------------------------------------------------------------------
# T-003 — Scheduled jobs
# ---------------------------------------------------------------------------
# In-process APScheduler audit + admin surface. The host runs no Celery /
# Redis per design, so this is an in-memory ``BackgroundScheduler``;
# scaling out to multiple workers in future is a swap for an
# SQLAlchemyJobStore + a coordinator lock.

# Allowed status values for KpiScheduledJobRun.status. ``running`` is
# set when the wrapper enters the job; flipped to ``success`` or
# ``failed`` when the function returns / raises. ``cancelled`` is for
# manual termination via the admin UI's "stop" affordance (future).
SCHEDULED_JOB_RUN_STATUSES = ("running", "success", "failed", "cancelled")


class KpiScheduledJobRun(KpiBase):
    """One execution of a registered scheduled job.

    Rows are inserted in the ``running`` state when the wrapper starts
    the job, then updated to ``success`` / ``failed`` when it exits.
    A crashed worker leaves rows stuck at ``running`` — surfacing those
    (last_updated_at + status filter) is how the admin UI shows
    "missed heartbeat" diagnostics.
    """
    __tablename__ = "kpi_scheduled_job_run"

    run_id = Column(Integer, primary_key=True, autoincrement=True)

    # ``job_name`` is the key used by ``services.scheduler.register`` and
    # also what appears in the admin list / "Run now" surface.
    job_name = Column(String(100), nullable=False)

    # ``cli`` | ``api_trigger`` | ``scheduled``. ``cli`` reserved for
    # future manual invocations from the eval CLI style entrypoint.
    trigger_source = Column(String(20), nullable=False, default="scheduled")
    triggered_by_user_id = Column(Integer, nullable=True)

    started_at = Column(DateTime, nullable=False, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)

    # See SCHEDULED_JOB_RUN_STATUSES.
    status = Column(String(20), nullable=False, default="running")
    error = Column(Text, nullable=True)

    # Job-defined integer for "how much work happened this run" — e.g.
    # rows reindexed, KPIs refreshed, change-log entries written. The
    # admin UI shows the rolling average so a job that suddenly drops
    # to 0 stands out as a likely regression.
    items_processed = Column(Integer, nullable=True)

    duration_ms = Column(Integer, nullable=True)

    # Free-form bag for per-job diagnostics — e.g.
    # ``{"snapshots_compared": 2, "tables_reindexed": 47}``. Reserved
    # for whatever the job wants to expose without growing a column.
    detail_json = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_kpi_scheduled_job_run_name_started", "job_name", "started_at"),
        Index("ix_kpi_scheduled_job_run_status", "status"),
    )


# ---------------------------------------------------------------------------
# T-001 — Eval harness
# ---------------------------------------------------------------------------
# Golden test cases for the NL→SQL agent + a per-run audit log. The runner
# (kpi_studio/eval/runner.py) reads cases, fires the full pipeline against
# each (preflight → agent → safety → execute), and writes one
# KpiEvalCaseResult per case under a parent KpiEvalRun. CI can compare the
# pass rate of a run against a prior baseline and block regressions.

# Allowed case status values written to KpiEvalCaseResult.status. ``pass``
# = every comparator green. ``fail`` = at least one comparator red but the
# pipeline ran to completion. ``error`` = pipeline blew up (provider down,
# DB error, etc.). ``skipped`` = case was deactivated or filtered out.
EVAL_CASE_STATUSES = ("pass", "fail", "error", "skipped")

# Why a case failed — a stable code per comparator, recorded as a list
# on KpiEvalCaseResult.failure_reasons. Keeps reports machine-readable.
EVAL_FAILURE_CODES = (
    "tables_missing",       # expected_tables not all present in produced SQL
    "tables_extra",         # produced SQL touches tables the case didn't expect
    "columns_missing",      # expected_columns not all referenced
    "row_count_low",        # produced_row_count < expected_row_count_min
    "row_count_high",       # produced_row_count > expected_row_count_max
    "sql_exec_failed",      # safety / executor raised
    "agent_no_proposal",    # agent exited without calling propose_sql
    "agent_timeout",        # token budget / iteration cap hit
    "provider_error",       # LLM provider returned non-2xx
)


class KpiEvalCase(KpiBase):
    """A single golden test case for the NL→SQL pipeline.

    Each case is a prompt plus the expectations the pipeline must satisfy
    when fed that prompt. Authoring is manual (or by promoting a
    high-rated chat turn via the auto-promotion flow in T-401). Failed
    comparators are recorded on KpiEvalCaseResult, never on the case row
    itself — the case is the spec, the run is the observation.
    """
    __tablename__ = "kpi_eval_case"

    case_id = Column(Integer, primary_key=True, autoincrement=True)

    # Short human-readable label shown in CLI output and the admin UI.
    # Not used for any matching — duplicates allowed but discouraged.
    name = Column(String(200), nullable=False)

    # The natural-language prompt to feed through the pipeline. Verbatim;
    # no preprocessing.
    prompt = Column(Text, nullable=False)

    # Expectations. All optional — a case may assert only some
    # comparators. Missing fields skip the corresponding comparator
    # rather than counting as a fail.
    #
    # ``expected_tables`` — list[str], table names that MUST appear in
    #   the agent's final SQL. Extras are allowed unless ``strict_tables``.
    # ``expected_columns`` — list[str], qualified names like
    #   "customer.name" that MUST appear in the SELECT list.
    # ``expected_row_count_min`` / ``expected_row_count_max`` — inclusive
    #   range the result row count must land within. Either can be null.
    # ``golden_sql`` — the canonical SQL a human would write. Not
    #   compared verbatim (SQL has many valid spellings); rendered in
    #   reports as a diff hint when the case fails.
    expected_tables = Column(JSON, nullable=True)
    expected_columns = Column(JSON, nullable=True)
    expected_row_count_min = Column(Integer, nullable=True)
    expected_row_count_max = Column(Integer, nullable=True)
    golden_sql = Column(Text, nullable=True)

    # If true, produced SQL touching any table OUTSIDE expected_tables
    # is a fail (tables_extra). Default false — we mostly care about
    # what's present, not what's absent.
    strict_tables = Column(Boolean, nullable=False, default=False)

    # Free-form labels for filtering: e.g., ``["critical"]``,
    # ``["adversarial", "tenant"]``, ``["regression-2026-Q2"]``.
    tags = Column(JSON, nullable=True)

    # Soft-delete flag. ``is_active=false`` cases are skipped by the
    # runner but kept for historical comparison.
    is_active = Column(Boolean, nullable=False, default=True)

    # Cached last-run summary so the admin list page doesn't have to
    # join against KpiEvalCaseResult on every render.
    last_pass_at = Column(DateTime, nullable=True)
    last_fail_reason = Column(Text, nullable=True)

    # Optional pin — when set, the case only runs against this schema
    # snapshot (used for cases asserting against a specific historical
    # shape during a migration).
    pinned_snapshot_id = Column(
        Integer,
        ForeignKey("kpi_schema_snapshot.snapshot_id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, nullable=False, default=_utcnow)
    created_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)
    updated_by = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_kpi_eval_case_active", "is_active"),
    )


class KpiEvalRun(KpiBase):
    """One invocation of the eval runner (CLI, CI hook, or API).

    Holds run-level totals and a snapshot of the knowledge versions
    that were live — so a degraded pass rate can be correlated against
    a prompt-version or schema-snapshot change.
    """
    __tablename__ = "kpi_eval_run"

    eval_run_id = Column(Integer, primary_key=True, autoincrement=True)

    started_at = Column(DateTime, nullable=False, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)

    # ``cli`` | ``ci`` | ``manual`` | ``scheduled`` (T-003). Recorded
    # so we can split metrics by trigger source.
    triggered_by = Column(String(20), nullable=False, default="cli")

    # Which user kicked it off (null for ``ci`` / ``scheduled``).
    triggered_by_user_id = Column(Integer, nullable=True)

    # Subset filter applied — null = all active cases ran. JSON list of
    # tag strings; the runner uses OR semantics across tags.
    tags_filter = Column(JSON, nullable=True)

    # Knowledge fingerprint at run-time. ``snapshot_id`` is FK; the
    # other two are free-form strings populated once T-002 ships
    # prompt versioning.
    snapshot_id = Column(
        Integer,
        ForeignKey("kpi_schema_snapshot.snapshot_id", ondelete="SET NULL"),
        nullable=True,
    )
    prompt_version = Column(String(20), nullable=True)
    glossary_version = Column(String(40), nullable=True)
    exemplar_set_hash = Column(String(64), nullable=True)

    # Aggregates — derivable from KpiEvalCaseResult but stored for cheap
    # list pages.
    cases_total = Column(Integer, nullable=False, default=0)
    cases_passed = Column(Integer, nullable=False, default=0)
    cases_failed = Column(Integer, nullable=False, default=0)
    cases_errored = Column(Integer, nullable=False, default=0)
    cases_skipped = Column(Integer, nullable=False, default=0)

    # Free-form bag for stats the CLI / CI hook wants to surface:
    # e.g. ``{"total_tokens": 12340, "wall_clock_s": 47.3}``.
    summary_json = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_kpi_eval_run_started", "started_at"),
    )


class KpiEvalCaseResult(KpiBase):
    """One case's outcome inside an eval run. Cascade-deleted with its run."""
    __tablename__ = "kpi_eval_case_result"

    result_id = Column(Integer, primary_key=True, autoincrement=True)

    eval_run_id = Column(
        Integer,
        ForeignKey("kpi_eval_run.eval_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id = Column(
        Integer,
        ForeignKey("kpi_eval_case.case_id", ondelete="CASCADE"),
        nullable=False,
    )

    # One of EVAL_CASE_STATUSES.
    status = Column(String(20), nullable=False)

    # What the agent actually produced. ``produced_sql`` is the
    # post-safety rewrite; the pre-rewrite version lives on
    # KpiNlRun.final_sql via ``nl_run_id``.
    produced_sql = Column(Text, nullable=True)
    produced_row_count = Column(Integer, nullable=True)
    tables_referenced = Column(JSON, nullable=True)
    columns_referenced = Column(JSON, nullable=True)

    # Which comparators tripped. Empty / null on pass. Each entry is a
    # code from EVAL_FAILURE_CODES.
    failure_reasons = Column(JSON, nullable=True)

    # Free-form per-comparator diagnostic — e.g.,
    # ``{"tables_missing": ["customer"], "row_count_low": {"got": 0, "min": 1}}``.
    failure_detail = Column(JSON, nullable=True)

    duration_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)

    # Link back to the KpiNlRun this case generated (replay /
    # debugging). Null if the pipeline never reached the agent stage.
    nl_run_id = Column(Integer, nullable=True)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_kpi_eval_result_run", "eval_run_id"),
        Index("ix_kpi_eval_result_case", "case_id"),
    )


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
    "KpiEvalCase",
    "KpiEvalRun",
    "KpiEvalCaseResult",
    "EVAL_CASE_STATUSES",
    "EVAL_FAILURE_CODES",
    "KpiScheduledJobRun",
    "SCHEDULED_JOB_RUN_STATUSES",
    "KpiLlmProviderConfig",
    "PROVIDER_KINDS",
    "KpiLlmCallLog",
    "CALL_LOG_SOURCES",
    "DASHBOARD_SCOPE_USER",
    "DASHBOARD_SCOPE_COMPANY",
    "CARD_SIZES",
]
