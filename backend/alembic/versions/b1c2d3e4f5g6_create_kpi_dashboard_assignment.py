"""Create kpi_dashboard_assignment (KPI Studio Phase A4)

Adds per-role and per-user grants on dashboards. Visibility expands to:
owner | scope=company AND same company | EXISTS assignment for me/my role
| SuperAdmin.

Owned by ``kpi_studio``. Model in ``backend/kpi_studio/models.py``.

Revision ID: b1c2d3e4f5g6
Revises: z0a1b2c3d4e5
Create Date: 2026-04-29

Note: the obvious next-in-sequence id ``a1b2c3d4e5f6`` was already taken
by the host's location/dia tables migration, so we shift one letter.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5g6"
down_revision: Union[str, None] = "z0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "kpi_dashboard_assignment",
        sa.Column("assignment_id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column(
            "dashboard_id", sa.Integer(),
            sa.ForeignKey("kpi_dashboard.dashboard_id", ondelete="CASCADE"),
            nullable=False,
        ),
        # role_id and user_id are referential by convention to RoleMaster /
        # UserMaster but no FK is declared — keeps the package portable.
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("granted_by", sa.Integer(), nullable=True),
        sa.Column(
            "granted_at", sa.DateTime(), nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_kpi_dash_assign_dashboard", "kpi_dashboard_assignment", ["dashboard_id"])
    op.create_index("ix_kpi_dash_assign_role", "kpi_dashboard_assignment", ["role_id"])
    op.create_index("ix_kpi_dash_assign_user", "kpi_dashboard_assignment", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_kpi_dash_assign_user", table_name="kpi_dashboard_assignment")
    op.drop_index("ix_kpi_dash_assign_role", table_name="kpi_dashboard_assignment")
    op.drop_index("ix_kpi_dash_assign_dashboard", table_name="kpi_dashboard_assignment")
    op.drop_table("kpi_dashboard_assignment")
