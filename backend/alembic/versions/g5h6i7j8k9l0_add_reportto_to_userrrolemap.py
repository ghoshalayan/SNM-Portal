"""Add reportTo column to UserRoleMap for company-specific reporting hierarchy

Revision ID: g5h6i7j8k9l0
Revises: f3a1b2c4d5e6
Create Date: 2026-03-31 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'g5h6i7j8k9l0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'UserRoleMap',
        sa.Column('reportTo', sa.Integer(), sa.ForeignKey('UserMaster.userId'), nullable=True),
    )

    # Migrate existing User.reportTo values into UserRoleMap rows
    # so existing org-tree assignments are preserved
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE urm SET urm.reportTo = u.reportTo "
            "FROM UserRoleMap urm "
            "INNER JOIN UserMaster u ON urm.userId = u.userId "
            "WHERE u.reportTo IS NOT NULL AND urm.isActive = 1"
        )
    )


def downgrade() -> None:
    op.drop_column('UserRoleMap', 'reportTo')
