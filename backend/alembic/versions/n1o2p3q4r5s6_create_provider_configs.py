"""Create kpi_llm_provider_config + migrate single-provider row into it.

Refactor for multi-provider support: each row in ``kpi_llm_provider_config``
is one configured LLM provider. The legacy single-provider columns on
``kpi_settings`` stay in place as a fallback for unmigrated stages.

Data migration: if the existing ``kpi_settings`` row has a provider +
API key set, we insert one row into ``kpi_llm_provider_config`` carrying
those values forward — display_name becomes "Migrated (<kind>)" so the
admin can rename it via the UI. The legacy columns are NOT cleared
(so a rollback of the application code can still find them).

Idempotent: probes ``INFORMATION_SCHEMA.TABLES`` before
``create_table``; the data migration also probes for an existing row
to avoid duplicates on re-run.

Revision ID: n1o2p3q4r5s6
Revises: m0n1o2p3q4r5
Create Date: 2026-05-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, None] = "m0n1o2p3q4r5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # ---- 1. Schema -----------------------------------------------------
    if not _table_exists(bind, "kpi_llm_provider_config"):
        op.create_table(
            "kpi_llm_provider_config",
            sa.Column("provider_config_id", sa.Integer(),
                      primary_key=True, autoincrement=True, nullable=False),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("api_key", sa.Text(), nullable=False),
            sa.Column("base_url", sa.String(length=500), nullable=True),
            sa.Column("openrouter_referer", sa.String(length=500), nullable=True),
            sa.Column("openrouter_app_name", sa.String(length=200), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False,
                      server_default=sa.text("1")),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False,
                      server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_by", sa.Integer(), nullable=True),
        )
        op.create_index("ix_kpi_provider_config_active",
                        "kpi_llm_provider_config", ["is_active"])
        op.create_index("ix_kpi_provider_config_kind",
                        "kpi_llm_provider_config", ["kind"])

    # ---- 2. Data migration -------------------------------------------
    # Only fires when (a) the new table is empty AND (b) the existing
    # kpi_settings row has a usable single-provider config.
    existing_count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM kpi_llm_provider_config"
    )).scalar() or 0
    if existing_count > 0:
        return

    src = bind.execute(sa.text(
        "SELECT TOP 1 llm_provider, openai_api_key, openai_model, "
        "openai_base_url, openrouter_referer, openrouter_app_name "
        "FROM kpi_settings"
    )).fetchone()
    if not src:
        return
    kind = (src[0] or "").strip().lower()
    api_key = (src[1] or "").strip()
    if not kind or not api_key:
        # No usable config to migrate — admin will add their first
        # provider via the UI.
        return

    base_url = (src[3] or "").strip() or None
    referer = (src[4] or "").strip() or None
    app_name = (src[5] or "").strip() or None
    bind.execute(sa.text(
        """
        INSERT INTO kpi_llm_provider_config
          (kind, display_name, api_key, base_url,
           openrouter_referer, openrouter_app_name,
           is_active, description, created_at, updated_at)
        VALUES
          (:kind, :display_name, :api_key, :base_url,
           :referer, :app_name,
           1, :description, GETDATE(), GETDATE())
        """
    ), {
        "kind": kind,
        "display_name": f"Migrated ({kind})",
        "api_key": api_key,
        "base_url": base_url,
        "referer": referer,
        "app_name": app_name,
        "description": (
            "Auto-created from the legacy single-provider settings row. "
            "Rename via the Settings → Providers tab."
        ),
    })


def downgrade() -> None:
    try:
        op.drop_table("kpi_llm_provider_config")
    except Exception:
        pass
