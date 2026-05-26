"""Add knowledge-fingerprint columns to NL audit rows (T-002).

Adds four columns to both ``kpi_nl_run`` and ``kpi_chat_message``:

* ``prompt_version``       — semantic MAJOR.MINOR.PATCH from ``KPI_PROMPT_VERSION``
                             env or KpiSettings (the system prompt's version stamp).
* ``glossary_version``     — monotonic glossary-state stamp; populated once
                             T-301 (structured glossary) ships. Nullable until then.
* ``schema_snapshot_id``   — FK → kpi_schema_snapshot; the introspection snapshot
                             the agent saw on this run.
* ``exemplar_set_hash``    — sha256 of the (sorted) exemplar IDs that contributed
                             to the prompt; populated once T-401 ships. Nullable
                             until then.

All four are nullable so historical rows survive the migration. Writers
in ``api/nl.py`` and ``services/chat_service.py`` populate them on every
new insert via ``services.knowledge_versions.current()``.

Idempotent — probes ``INFORMATION_SCHEMA.COLUMNS`` before each
``add_column`` so re-runs are no-ops.

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
Create Date: 2026-05-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k8l9m0n1o2p3"
down_revision: Union[str, None] = "j7k8l9m0n1o2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column, type, fk_target?) tuples — single source of truth.
COLS = [
    ("kpi_nl_run", "prompt_version", sa.String(length=20), None),
    ("kpi_nl_run", "glossary_version", sa.String(length=40), None),
    ("kpi_nl_run", "schema_snapshot_id", sa.Integer(),
     ("kpi_schema_snapshot", "snapshot_id")),
    ("kpi_nl_run", "exemplar_set_hash", sa.String(length=64), None),
    ("kpi_chat_message", "prompt_version", sa.String(length=20), None),
    ("kpi_chat_message", "glossary_version", sa.String(length=40), None),
    ("kpi_chat_message", "schema_snapshot_id", sa.Integer(),
     ("kpi_schema_snapshot", "snapshot_id")),
    ("kpi_chat_message", "exemplar_set_hash", sa.String(length=64), None),
]

INDICES = [
    ("ix_kpi_nl_run_prompt_version", "kpi_nl_run", ["prompt_version"]),
    ("ix_kpi_chat_message_prompt_version", "kpi_chat_message", ["prompt_version"]),
]


def _column_exists(bind, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(bind, table: str, name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(ix.get("name") == name for ix in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, col_type, fk in COLS:
        if _column_exists(bind, table, column):
            continue
        kwargs = {"nullable": True}
        col = sa.Column(column, col_type, **kwargs)
        op.add_column(table, col)
        if fk is not None:
            ref_table, ref_col = fk
            try:
                op.create_foreign_key(
                    f"fk_{table}_{column}_{ref_table}",
                    table, ref_table, [column], [ref_col],
                    ondelete="SET NULL",
                )
            except Exception:
                # Some SQL Server installs can't create cross-table FKs in
                # the same transaction as the column add. Non-fatal — the
                # logical link still works through the ORM relationship.
                pass
    for index_name, table, cols in INDICES:
        if _index_exists(bind, table, index_name):
            continue
        try:
            op.create_index(index_name, table, cols)
        except Exception:
            pass


def downgrade() -> None:
    # Drop indices first, then columns. FKs auto-drop with their column.
    for index_name, table, _cols in INDICES:
        try:
            op.drop_index(index_name, table_name=table)
        except Exception:
            pass
    for table, column, _t, _fk in COLS:
        try:
            op.drop_column(table, column)
        except Exception:
            pass
