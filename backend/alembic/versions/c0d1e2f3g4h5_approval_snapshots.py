"""Soft-flow approval snapshot tables.

Adds ``QuotViabilityApprovalSnapshot`` and ``QuotAnnexureApprovalSnapshot``.
Each row freezes the full state of a viability sheet / annexure at the
instant Approve fired — captured as a JSON document so the head row
can keep being edited under the soft-flow model without losing the
"what was approved" answer for audit / dispute / regulatory purposes.

See ``backend/app/models/approval_snapshot.py`` for the model commentary.

Schema notes:

* ``snapshotData`` is ``NVARCHAR(MAX)`` on SQL Server (the engine the
  app targets). SQLAlchemy maps ``NVARCHAR(None)`` to that.
* No CASCADE on the parent FK — if a head row gets soft-deleted later,
  the snapshot must survive as the audit trail.
* Index on ``(viabilityId / annexureId, snapshotId DESC)`` so the
  "fetch latest approved snapshot" query is a single index seek.

Revision ID: c0d1e2f3g4h5
Revises: b9c0d1e2f3g4
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mssql import NVARCHAR


# revision identifiers, used by Alembic.
revision: str = "c0d1e2f3g4h5"
down_revision: Union[str, None] = "b9c0d1e2f3g4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- Viability approval snapshot --------------------------------
    op.create_table(
        "QuotViabilityApprovalSnapshot",
        sa.Column("snapshotId", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("companyId", sa.Integer(), nullable=False),
        sa.Column("viabilityId", sa.Integer(), nullable=False),
        sa.Column("quotId", sa.Integer(), nullable=False),
        sa.Column("versionNo", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["viabilityId"], ["QuotViabilitySheet.viabilityId"]),
        sa.ForeignKeyConstraint(["quotId"], ["QuotSummary.quotId"]),
        sa.ForeignKeyConstraint(["approvedByUserId"], ["UserMaster.userId"]),
        sa.PrimaryKeyConstraint("snapshotId"),
    )
    op.create_index(
        "ix_QuotViabilityApprovalSnapshot_sheet_latest",
        "QuotViabilityApprovalSnapshot",
        ["viabilityId", "snapshotId"],
        unique=False,
    )

    # ---- Annexure approval snapshot ---------------------------------
    op.create_table(
        "QuotAnnexureApprovalSnapshot",
        sa.Column("snapshotId", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("companyId", sa.Integer(), nullable=False),
        sa.Column("annexureId", sa.Integer(), nullable=False),
        sa.Column("quotId", sa.Integer(), nullable=False),
        sa.Column("versionNo", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["annexureId"], ["QuotAnnexure.annexureId"]),
        sa.ForeignKeyConstraint(["quotId"], ["QuotSummary.quotId"]),
        sa.ForeignKeyConstraint(["approvedByUserId"], ["UserMaster.userId"]),
        sa.PrimaryKeyConstraint("snapshotId"),
    )
    op.create_index(
        "ix_QuotAnnexureApprovalSnapshot_ann_latest",
        "QuotAnnexureApprovalSnapshot",
        ["annexureId", "snapshotId"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_QuotAnnexureApprovalSnapshot_ann_latest",
        table_name="QuotAnnexureApprovalSnapshot",
    )
    op.drop_table("QuotAnnexureApprovalSnapshot")
    op.drop_index(
        "ix_QuotViabilityApprovalSnapshot_sheet_latest",
        table_name="QuotViabilityApprovalSnapshot",
    )
    op.drop_table("QuotViabilityApprovalSnapshot")
