"""Add is_default + default_model to kpi_llm_provider_config.

Two columns:

* ``default_model`` NVARCHAR(200) NULL — admin-entered default model
  string for this provider. New providers MUST supply this (the UI
  pre-fills from KIND_DEFAULTS when the kind is picked). Existing rows
  are back-filled from the kind's hardcoded default so nothing breaks.

* ``is_default`` BIT NOT NULL DEFAULT 0 — exactly one provider config
  is the "system default" at any time; stage routing falls back to
  this provider's ``default_model`` when a stage has no per-stage
  override. The service layer enforces the single-default invariant
  (setting one True unsets all others in the same transaction).

Back-fill on upgrade:
- ``default_model`` populated from the kind's hardcoded value (matches
  ``provider_config_service.KIND_DEFAULTS``). Anything we don't know
  about gets an empty string and the admin edits it.
- The first active provider is marked ``is_default=1`` so the resolver
  has a fallback target from the moment the migration runs.

Idempotent.

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-05-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q4r5s6t7u8v9"
down_revision: Union[str, None] = "p3q4r5s6t7u8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Same map as provider_config_service.KIND_DEFAULTS — duplicated here
# so the back-fill SQL doesn't depend on importing application code at
# migration time. Keep these two in sync when adding a new kind.
KIND_DEFAULT_MODELS = {
    "openai":       "gpt-5.4-nano",
    "openrouter":   "anthropic/claude-3.5-sonnet",
    "cerebras":     "llama-3.3-70b",
    "ollama_cloud": "llama3.3",
    "azure_openai": "gpt-4o",
}


def _has_col(table: str, col: str) -> bool:
    conn = op.get_bind()
    n = conn.execute(sa.text(
        "SELECT COUNT(*) FROM sys.columns "
        "WHERE object_id = OBJECT_ID(:t) AND name = :c"
    ), {"t": table, "c": col}).scalar()
    return bool(n)


def upgrade() -> None:
    if not _has_col("kpi_llm_provider_config", "default_model"):
        op.add_column(
            "kpi_llm_provider_config",
            sa.Column("default_model", sa.String(length=200), nullable=True),
        )

    if not _has_col("kpi_llm_provider_config", "is_default"):
        # NULLable first so back-fill can run without violating the
        # NOT NULL constraint; we tighten it after the UPDATE.
        op.add_column(
            "kpi_llm_provider_config",
            sa.Column("is_default", sa.Boolean(), nullable=True),
        )

    conn = op.get_bind()

    # Back-fill default_model from the kind's hardcoded default. Only
    # touches rows where default_model IS NULL so admins who edit a
    # row before re-running this migration don't get clobbered.
    for kind, model in KIND_DEFAULT_MODELS.items():
        conn.execute(sa.text(
            "UPDATE kpi_llm_provider_config "
            "SET default_model = :m "
            "WHERE kind = :k AND (default_model IS NULL OR default_model = '')"
        ), {"k": kind, "m": model})

    # Initialise is_default: 0 everywhere, then promote the first
    # active row (lowest id) to True so the resolver has a fallback.
    conn.execute(sa.text(
        "UPDATE kpi_llm_provider_config SET is_default = 0 "
        "WHERE is_default IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE kpi_llm_provider_config SET is_default = 1 "
        "WHERE provider_config_id = ("
        "  SELECT TOP 1 provider_config_id FROM kpi_llm_provider_config "
        "  WHERE is_active = 1 ORDER BY provider_config_id ASC"
        ") AND NOT EXISTS ("
        "  SELECT 1 FROM kpi_llm_provider_config WHERE is_default = 1"
        ")"
    ))

    # Tighten is_default to NOT NULL with a server default of 0.
    op.alter_column(
        "kpi_llm_provider_config", "is_default",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("0"),
    )

    # Partial-style index — we'd ideally have a filtered unique index
    # on is_default=1 to enforce single-default at the DB level, but
    # SQL Server's filtered indexes need explicit recreation on
    # version upgrades and the service layer enforces this invariant
    # anyway. Stick to a regular non-unique helper index for the
    # "find the default" query path.
    op.create_index(
        "ix_kpi_provider_config_default",
        "kpi_llm_provider_config", ["is_default"],
    )


def downgrade() -> None:
    if _has_col("kpi_llm_provider_config", "default_model"):
        op.drop_column("kpi_llm_provider_config", "default_model")

    if _has_col("kpi_llm_provider_config", "is_default"):
        try:
            op.drop_index(
                "ix_kpi_provider_config_default",
                table_name="kpi_llm_provider_config",
            )
        except Exception:
            pass
        op.drop_column("kpi_llm_provider_config", "is_default")
