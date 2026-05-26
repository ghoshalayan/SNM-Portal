"""Create KPI Studio eval-harness tables (T-001).

Owned by ``kpi_studio``. Models in ``backend/kpi_studio/models.py``
(KpiEvalCase, KpiEvalRun, KpiEvalCaseResult). The runner lives at
``backend/kpi_studio/eval/runner.py``.

Three tables:

* ``kpi_eval_case``         — golden case spec (prompt + expectations).
* ``kpi_eval_run``          — one runner invocation; aggregates.
* ``kpi_eval_case_result``  — per-case outcome inside a run.

Idempotent: re-running on a DB where these tables already exist is a
no-op (guarded by inspector probes).

Revision ID: j7k8l9m0n1o2
Revises: i6j7k8l9m0n1
Create Date: 2026-05-23

History note: originally authored with revision id ``i6j7k8l9m0n1`` and
``down_revision = "h5i6j7k8l9m0"`` — both clashed with the parallel
chain (``h5i6j7k8l9m0_add_kpi_dashboard_item_grid.py`` existed
pre-this-branch and the FWS-perms migration was renamed to
``i6j7k8l9m0n1`` to serve as the merge migration collapsing the two
heads). Renumbered here to ``j7k8l9m0n1o2`` and chained off the
merge migration so ``alembic upgrade head`` works again.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j7k8l9m0n1o2"
down_revision: Union[str, None] = "i6j7k8l9m0n1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, name: str) -> bool:
    return name in sa.inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    # ---- kpi_eval_case ---------------------------------------------------
    if not _table_exists(bind, "kpi_eval_case"):
        op.create_table(
            "kpi_eval_case",
            sa.Column("case_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("expected_tables", sa.JSON(), nullable=True),
            sa.Column("expected_columns", sa.JSON(), nullable=True),
            sa.Column("expected_row_count_min", sa.Integer(), nullable=True),
            sa.Column("expected_row_count_max", sa.Integer(), nullable=True),
            sa.Column("golden_sql", sa.Text(), nullable=True),
            sa.Column("strict_tables", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("tags", sa.JSON(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_pass_at", sa.DateTime(), nullable=True),
            sa.Column("last_fail_reason", sa.Text(), nullable=True),
            sa.Column(
                "pinned_snapshot_id", sa.Integer(),
                sa.ForeignKey("kpi_schema_snapshot.snapshot_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_by", sa.Integer(), nullable=True),
        )
        op.create_index("ix_kpi_eval_case_active", "kpi_eval_case", ["is_active"])

    # ---- kpi_eval_run ----------------------------------------------------
    if not _table_exists(bind, "kpi_eval_run"):
        op.create_table(
            "kpi_eval_run",
            sa.Column("eval_run_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("triggered_by", sa.String(length=20), nullable=False, server_default="cli"),
            sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
            sa.Column("tags_filter", sa.JSON(), nullable=True),
            sa.Column(
                "snapshot_id", sa.Integer(),
                sa.ForeignKey("kpi_schema_snapshot.snapshot_id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("prompt_version", sa.String(length=20), nullable=True),
            sa.Column("glossary_version", sa.String(length=40), nullable=True),
            sa.Column("exemplar_set_hash", sa.String(length=64), nullable=True),
            sa.Column("cases_total", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_passed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_failed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_errored", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cases_skipped", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary_json", sa.JSON(), nullable=True),
        )
        op.create_index("ix_kpi_eval_run_started", "kpi_eval_run", ["started_at"])

    # ---- kpi_eval_case_result --------------------------------------------
    if not _table_exists(bind, "kpi_eval_case_result"):
        op.create_table(
            "kpi_eval_case_result",
            sa.Column("result_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column(
                "eval_run_id", sa.Integer(),
                sa.ForeignKey("kpi_eval_run.eval_run_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "case_id", sa.Integer(),
                sa.ForeignKey("kpi_eval_case.case_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("produced_sql", sa.Text(), nullable=True),
            sa.Column("produced_row_count", sa.Integer(), nullable=True),
            sa.Column("tables_referenced", sa.JSON(), nullable=True),
            sa.Column("columns_referenced", sa.JSON(), nullable=True),
            sa.Column("failure_reasons", sa.JSON(), nullable=True),
            sa.Column("failure_detail", sa.JSON(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("tokens_used", sa.Integer(), nullable=True),
            sa.Column("nl_run_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_kpi_eval_result_run", "kpi_eval_case_result", ["eval_run_id"])
        op.create_index("ix_kpi_eval_result_case", "kpi_eval_case_result", ["case_id"])


def downgrade() -> None:
    # Cascade ordering: results → run → case.
    for tbl in ("kpi_eval_case_result", "kpi_eval_run", "kpi_eval_case"):
        try:
            op.drop_table(tbl)
        except Exception:
            pass
