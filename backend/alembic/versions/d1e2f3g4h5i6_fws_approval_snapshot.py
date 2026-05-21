"""FWS approval snapshot table (Slice A — soft-flow versioning).

Adds ``QuotFWSApprovalSnapshot`` so the Final Working Sheet gets the
same Approve-creates-version workflow as viability and annexure. The
FWS itself remains a flat per-line collection — the snapshot table
captures it as a single JSON document per Approve action.

Per-cycle versioning (D4 decision 2026-05-20): ``versionNo`` starts at
1 within each cycle. The frontend renders ``C{cycleNo}-V{versionNo}``
for display.

D3 short-circuit (content-hash equality) is enforced at the service
layer, not the DB. The ``contentHash`` column is stored so the next
Approve can compare cheaply without re-hashing every line row.

Revision ID: d1e2f3g4h5i6
Revises: c0d1e2f3g4h5
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


revision: str = "d1e2f3g4h5i6"
down_revision: Union[str, None] = "c0d1e2f3g4h5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "QuotFWSApprovalSnapshot",
        sa.Column("snapshotId", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("companyId", sa.Integer(), nullable=False),
        sa.Column("quotOrderCycleId", sa.Integer(), nullable=False),
        sa.Column("quotId", sa.Integer(), nullable=False),
        sa.Column("versionNo", sa.Integer(), nullable=False),
        sa.Column("contentHash", sa.String(length=64), nullable=False),
        sa.Column("approvedByUserId", sa.Integer(), nullable=True),
        sa.Column("approvedByName", sa.String(length=200), nullable=True),
        sa.Column("approvedAt", sa.DateTime(), nullable=False),
        sa.Column("snapshotData", NVARCHAR(None), nullable=False),
        # AuditMixin
        sa.Column("createdon", sa.DateTime(), nullable=True),
        sa.Column("createdby", sa.Integer(), nullable=True),
        sa.Column("lastupdateon", sa.DateTime(), nullable=True),
        sa.Column("lastupdateby", sa.Integer(), nullable=True),
        sa.Column("isActive", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.ForeignKeyConstraint(["companyId"], ["Company.companyId"]),
        sa.ForeignKeyConstraint(["quotOrderCycleId"], ["QuotOrderCycle.quotOrderCycleId"]),
        sa.ForeignKeyConstraint(["quotId"], ["QuotSummary.quotId"]),
        sa.ForeignKeyConstraint(["approvedByUserId"], ["UserMaster.userId"]),
        sa.PrimaryKeyConstraint("snapshotId"),
    )
    # Composite index: "latest snapshot for this cycle" lookup is the hot
    # path (re-approve + default-selection in generators), and the
    # ``snapshotId DESC`` ordering takes advantage of the implicit index
    # direction here.
    op.create_index(
        "ix_QuotFWSApprovalSnapshot_cycle_latest",
        "QuotFWSApprovalSnapshot",
        ["quotOrderCycleId", "snapshotId"],
        unique=False,
    )
    # Unique on (cycle, versionNo) so per-cycle numbering is enforced at
    # the DB — even if two concurrent Approve calls race, only one
    # version row per cycle per integer can land.
    op.create_index(
        "uq_QuotFWSApprovalSnapshot_cycle_version",
        "QuotFWSApprovalSnapshot",
        ["quotOrderCycleId", "versionNo"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_QuotFWSApprovalSnapshot_cycle_version",
        table_name="QuotFWSApprovalSnapshot",
    )
    op.drop_index(
        "ix_QuotFWSApprovalSnapshot_cycle_latest",
        table_name="QuotFWSApprovalSnapshot",
    )
    op.drop_table("QuotFWSApprovalSnapshot")
