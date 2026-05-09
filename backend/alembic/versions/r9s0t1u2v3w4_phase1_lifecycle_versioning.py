"""Phase 1: lifecycle versioning + Convert + Unlock-and-Edit scaffolding.

Schema-only DDL for the Quotation→Annexure lifecycle refactor. This
migration adds:

* **Per-stage versioning** — ``parentXxxId`` + ``versionNo`` on
  ``QuotPurchaseOrder``, ``QuotViabilitySheet``, ``QuotAnnexure``.
  Mirrors the existing ``QuotSummary.parentQuotId / versionNo``
  pattern. Existing rows are backfilled with ``versionNo=1`` and
  ``parentXxxId=NULL``.
* **Convert action** — ``convertedOn`` / ``convertedBy`` on
  ``QuotSummary``. The forward gate from Stage 1 (Approved) to
  Stage 2 (PO capture) is now an explicit Convert action, not the
  legacy ``Matured`` rename. Status rename + backfill happens in
  the next migration so this one stays purely additive.
* **Permission flags** — new ``Can*`` columns on ``RoleMenuMap``
  for the new actions (Convert / Reactivate / SubmitPO / RejectPO /
  ApproveViability) and per-stage Unlock-and-Edit. Seeding to role
  templates happens in the next migration.
* **LifecycleUnlockAudit table** — every Unlock-and-Edit writes a row
  here with stage / entityId / unlockedBy / unlockedOn / reason. Gives
  admins an audit trail for the privileged escape valve.

Revision ID: r9s0t1u2v3w4
Revises: q8r9s0t1u2v3
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "r9s0t1u2v3w4"
down_revision: Union[str, None] = "q8r9s0t1u2v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Permission flags added to RoleMenuMap. All default to 0; seeding to
# the canonical role templates per company happens in the migration
# that runs immediately after this one.
_NEW_ROLE_MENU_FLAGS = (
    "CanConvert",
    "CanReactivate",
    "CanSubmitPO",
    "CanRejectPO",
    "CanApproveViability",
    "CanUnlockEditQuotation",
    "CanUnlockEditPO",
    "CanUnlockEditViability",
    "CanUnlockEditAnnexure",
)


def upgrade() -> None:
    # ----- 1) Per-stage versioning columns -----
    # All three downstream entities adopt the same chain shape as
    # QuotSummary: parent FK to self, integer versionNo. Existing rows
    # become v1 of their chain.
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column(
            "parentPOId", sa.Integer,
            sa.ForeignKey("QuotPurchaseOrder.quotPOId"),
            nullable=True,
        ),
    )
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column(
            "versionNo", sa.Integer,
            nullable=False, server_default=sa.text("1"),
        ),
    )
    op.alter_column("QuotPurchaseOrder", "versionNo", server_default=None)

    # PO status. Existing rows came into being only when "Mature" was
    # clicked under the old flow — i.e. they were effectively already
    # submitted. Backfill with 'Submitted' via server_default, then
    # clear the server_default so new rows under the v2 flow start at
    # the Python-side default of 'Draft' (set on the SA model).
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column(
            "status", sa.String(20),
            nullable=False, server_default=sa.text("'Submitted'"),
        ),
    )
    op.alter_column("QuotPurchaseOrder", "status", server_default=None)

    op.add_column(
        "QuotViabilitySheet",
        sa.Column(
            "parentViabilityId", sa.Integer,
            sa.ForeignKey("QuotViabilitySheet.viabilityId"),
            nullable=True,
        ),
    )
    op.add_column(
        "QuotViabilitySheet",
        sa.Column(
            "versionNo", sa.Integer,
            nullable=False, server_default=sa.text("1"),
        ),
    )
    op.alter_column("QuotViabilitySheet", "versionNo", server_default=None)

    op.add_column(
        "QuotAnnexure",
        sa.Column(
            "parentAnnexureId", sa.Integer,
            sa.ForeignKey("QuotAnnexure.annexureId"),
            nullable=True,
        ),
    )
    op.add_column(
        "QuotAnnexure",
        sa.Column(
            "versionNo", sa.Integer,
            nullable=False, server_default=sa.text("1"),
        ),
    )
    op.alter_column("QuotAnnexure", "versionNo", server_default=None)

    # ----- 2) Convert columns on QuotSummary -----
    # Audit pair for the new Convert action. Backfill (for rows that
    # are already past the convert point) happens in the status-rename
    # migration so the convertedOn matches the lastupdateon at that
    # time — most accurate proxy we have.
    op.add_column(
        "QuotSummary",
        sa.Column("convertedOn", sa.DateTime, nullable=True),
    )
    op.add_column(
        "QuotSummary",
        sa.Column(
            "convertedBy", sa.Integer,
            sa.ForeignKey("UserMaster.userId"),
            nullable=True,
        ),
    )

    # ----- 3) New permission flags on RoleMenuMap -----
    for flag in _NEW_ROLE_MENU_FLAGS:
        op.add_column(
            "RoleMenuMap",
            sa.Column(
                flag, sa.Boolean(),
                nullable=False, server_default=sa.text("0"),
            ),
        )
        op.alter_column("RoleMenuMap", flag, server_default=None)

    # ----- 4) LifecycleUnlockAudit table -----
    # One row per Unlock-and-Edit action across any stage. Soft-delete
    # via isActive (kept consistent with the rest of the schema even
    # though audit rows are typically immutable in practice).
    op.create_table(
        "LifecycleUnlockAudit",
        sa.Column("auditId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "companyId", sa.Integer,
            sa.ForeignKey("Company.companyId"),
            nullable=False,
        ),
        # 'Quotation' | 'PurchaseOrder' | 'Viability' | 'Annexure'
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("entityId", sa.Integer, nullable=False),
        sa.Column(
            "unlockedBy", sa.Integer,
            sa.ForeignKey("UserMaster.userId"),
            nullable=False,
        ),
        sa.Column("unlockedOn", sa.DateTime, nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        # AuditMixin parity
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
    )
    # Common access pattern: "show me all unlocks on annexure X" or
    # "show me all unlocks by user Y" — index both.
    op.create_index(
        "IX_LifecycleUnlockAudit_stage_entity",
        "LifecycleUnlockAudit",
        ["stage", "entityId"],
    )
    op.create_index(
        "IX_LifecycleUnlockAudit_unlockedBy",
        "LifecycleUnlockAudit",
        ["unlockedBy"],
    )


def downgrade() -> None:
    op.drop_index(
        "IX_LifecycleUnlockAudit_unlockedBy",
        table_name="LifecycleUnlockAudit",
    )
    op.drop_index(
        "IX_LifecycleUnlockAudit_stage_entity",
        table_name="LifecycleUnlockAudit",
    )
    op.drop_table("LifecycleUnlockAudit")

    for flag in _NEW_ROLE_MENU_FLAGS:
        op.drop_column("RoleMenuMap", flag)

    op.drop_column("QuotSummary", "convertedBy")
    op.drop_column("QuotSummary", "convertedOn")

    op.drop_column("QuotAnnexure", "versionNo")
    op.drop_column("QuotAnnexure", "parentAnnexureId")
    op.drop_column("QuotViabilitySheet", "versionNo")
    op.drop_column("QuotViabilitySheet", "parentViabilityId")
    op.drop_column("QuotPurchaseOrder", "status")
    op.drop_column("QuotPurchaseOrder", "versionNo")
    op.drop_column("QuotPurchaseOrder", "parentPOId")
