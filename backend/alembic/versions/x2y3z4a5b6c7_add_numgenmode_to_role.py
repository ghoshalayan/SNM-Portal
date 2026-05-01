"""Add numGenMode column to RoleMaster

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
Create Date: 2026-04-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "x2y3z4a5b6c7"
down_revision: Union[str, None] = "w1x2y3z4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "RoleMaster",
        sa.Column("numGenMode", sa.String(20), server_default="select_code", nullable=False),
    )
    # Set all existing roles to select_code
    op.execute("UPDATE RoleMaster SET numGenMode = 'select_code'")
    # Change the default for new roles going forward
    op.alter_column("RoleMaster", "numGenMode", server_default="select_code")


def downgrade() -> None:
    op.drop_column("RoleMaster", "numGenMode")
