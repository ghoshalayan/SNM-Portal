"""Create scheduled-job audit table (T-003).

One table — ``kpi_scheduled_job_run`` — records every execution of
every registered scheduled job. The schedule itself is *not* persisted;
jobs are declared in-code via ``services.scheduler.register`` so they
are version-controlled and reproducible across environments. Stuck
``running`` rows surface as "missed heartbeat" diagnostics in the
admin UI.

Idempotent: probes ``INFORMATION_SCHEMA.TABLES`` before
``create_table``.

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l9m0n1o2p3q4"
down_revision: Union[str, None] = "k8l9m0n1o2p3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "kpi_scheduled_job_run"):
        return
    op.create_table(
        "kpi_scheduled_job_run",
        sa.Column("run_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("trigger_source", sa.String(length=20), nullable=False, server_default="scheduled"),
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("items_processed", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("detail_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_kpi_scheduled_job_run_name_started",
        "kpi_scheduled_job_run", ["job_name", "started_at"],
    )
    op.create_index(
        "ix_kpi_scheduled_job_run_status",
        "kpi_scheduled_job_run", ["status"],
    )


def downgrade() -> None:
    try:
        op.drop_table("kpi_scheduled_job_run")
    except Exception:
        pass
