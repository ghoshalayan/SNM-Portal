"""Phase 1A — LOI / Cycle CR data model.

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-05-18 12:00:00.000000

See ``MultiplePO-LOI-Cycle-CR.md`` for the full design. Summary:

  * Creates the new ``QuotOrderCycle`` table — the call-off cycle
    grouping under a quotation.
  * Adds ``quotOrderCycleId`` (FK → QuotOrderCycle) to four child
    tables: ``QuotPurchaseOrder``, ``QuotPOWorkingSheet``,
    ``QuotViabilitySheet``, ``QuotAnnexure``. Also to
    ``LifecycleUnlockAudit`` (stays nullable — Stage-1 audits don't
    have a cycle).
  * Adds ``isLOI`` (BIT) + ``loiSequence`` (INT) to ``QuotPurchaseOrder``.
  * Adds two new RBAC flags to ``RoleMenuMap``: ``CanCaptureLOI`` and
    ``CanStartNewCycle``.
  * Backfills every existing quotation that has downstream artifacts
    as Cycle #1. Updates the four child tables to point at that cycle.
  * Drops the UNIQUE filtered index on ``QuotPurchaseOrder.quotId``
    (was the 1:1 constraint blocking multi-PO).
  * Flips ``quotOrderCycleId`` to NOT NULL on the four main child
    tables. (``LifecycleUnlockAudit.quotOrderCycleId`` stays nullable.)

The migration is fully additive until the NOT-NULL alter at the end,
so legacy single-PO behaviour continues to work mid-migration. The
backfill is idempotent (re-running creates 0 new cycles).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "z7a8b9c0d1e2"
down_revision: Union[str, None] = "y6z7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1) Create the new QuotOrderCycle table
    # ------------------------------------------------------------------
    op.create_table(
        "QuotOrderCycle",
        sa.Column("quotOrderCycleId", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("companyId", sa.Integer, sa.ForeignKey("Company.companyId"), nullable=False),
        sa.Column("quotId", sa.Integer, sa.ForeignKey("QuotSummary.quotId"), nullable=False),
        sa.Column("cycleNo", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="Active"),
        sa.Column(
            "parentCycleId", sa.Integer,
            sa.ForeignKey("QuotOrderCycle.quotOrderCycleId"),
            nullable=True,
        ),
        sa.Column("startedOn", sa.DateTime, nullable=False),
        sa.Column("startedBy", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=False),
        sa.Column("closedOn", sa.DateTime, nullable=True),
        sa.Column("closedBy", sa.Integer, sa.ForeignKey("UserMaster.userId"), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        # AuditMixin columns
        sa.Column("createdon", sa.DateTime, nullable=True),
        sa.Column("createdby", sa.Integer, nullable=True),
        sa.Column("lastupdateon", sa.DateTime, nullable=True),
        sa.Column("lastupdateby", sa.Integer, nullable=True),
        sa.Column("isActive", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )
    op.create_index(
        "uq_quot_order_cycle_quot_cycle_no",
        "QuotOrderCycle",
        ["quotId", "cycleNo"],
        unique=True,
        mssql_where=sa.text("isActive = 1"),
    )
    op.create_index(
        "ix_quot_order_cycle_quot_status",
        "QuotOrderCycle",
        ["quotId", "status"],
    )
    op.create_index(
        "ix_quot_order_cycle_company",
        "QuotOrderCycle",
        ["companyId"],
    )

    # ------------------------------------------------------------------
    # 2) Add columns to existing tables (all nullable for now)
    # ------------------------------------------------------------------
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column(
            "quotOrderCycleId", sa.Integer,
            sa.ForeignKey("QuotOrderCycle.quotOrderCycleId"),
            nullable=True,
        ),
    )
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column("isLOI", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "QuotPurchaseOrder",
        sa.Column("loiSequence", sa.Integer, nullable=True),
    )

    op.add_column(
        "QuotPOWorkingSheet",
        sa.Column(
            "quotOrderCycleId", sa.Integer,
            sa.ForeignKey("QuotOrderCycle.quotOrderCycleId"),
            nullable=True,
        ),
    )
    op.add_column(
        "QuotViabilitySheet",
        sa.Column(
            "quotOrderCycleId", sa.Integer,
            sa.ForeignKey("QuotOrderCycle.quotOrderCycleId"),
            nullable=True,
        ),
    )
    op.add_column(
        "QuotAnnexure",
        sa.Column(
            "quotOrderCycleId", sa.Integer,
            sa.ForeignKey("QuotOrderCycle.quotOrderCycleId"),
            nullable=True,
        ),
    )
    op.add_column(
        "LifecycleUnlockAudit",
        sa.Column(
            "quotOrderCycleId", sa.Integer,
            sa.ForeignKey("QuotOrderCycle.quotOrderCycleId"),
            nullable=True,
        ),
    )

    # New RBAC flags. server_default=0 keeps existing custom roles
    # safe (they get OFF by default); role-template seeding migration
    # will turn them on for KRO+ / HOD+ in a follow-up.
    op.add_column(
        "RoleMenuMap",
        sa.Column("CanCaptureLOI", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "RoleMenuMap",
        sa.Column("CanStartNewCycle", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )

    # ------------------------------------------------------------------
    # 3) Backfill: every quotation with downstream artifacts gets
    #    Cycle #1. We derive ``status`` from the most-advanced
    #    downstream artifact:
    #      Active   — anything still Draft
    #      Complete — annexure exists and is Approved
    #    Started_by / startedOn — fall back to quotation.lastupdateby /
    #    lastupdateon since the original cycle event wasn't captured.
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO QuotOrderCycle (
            companyId, quotId, cycleNo, status,
            startedOn, startedBy, isActive
        )
        SELECT
            q.companyId,
            q.quotId,
            1                                       AS cycleNo,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM QuotAnnexure a
                    WHERE a.quotId = q.quotId
                      AND a.isActive = 1
                      AND a.status = 'Approved'
                ) THEN 'Complete'
                ELSE 'Active'
            END                                     AS status,
            COALESCE(q.lastupdateon, q.createdon, SYSUTCDATETIME()) AS startedOn,
            COALESCE(q.lastupdateby, q.createdby, 0) AS startedBy,
            1                                       AS isActive
        FROM QuotSummary q
        WHERE q.isActive = 1
          AND (
            EXISTS (SELECT 1 FROM QuotPurchaseOrder p
                    WHERE p.quotId = q.quotId AND p.isActive = 1)
            OR EXISTS (SELECT 1 FROM QuotPOWorkingSheet w
                    JOIN QuotPurchaseOrder po ON po.quotPOId = w.quotPOId
                    WHERE po.quotId = q.quotId AND w.isActive = 1)
            OR EXISTS (SELECT 1 FROM QuotViabilitySheet v
                    WHERE v.quotId = q.quotId AND v.isActive = 1)
            OR EXISTS (SELECT 1 FROM QuotAnnexure a
                    WHERE a.quotId = q.quotId AND a.isActive = 1)
          )
          AND NOT EXISTS (
            SELECT 1 FROM QuotOrderCycle c WHERE c.quotId = q.quotId
          );
    """)

    # ------------------------------------------------------------------
    # 4) Stitch the four child tables to the newly-inserted cycles.
    # ------------------------------------------------------------------
    op.execute("""
        UPDATE p
        SET p.quotOrderCycleId = c.quotOrderCycleId
        FROM QuotPurchaseOrder p
        JOIN QuotOrderCycle c ON c.quotId = p.quotId AND c.cycleNo = 1
        WHERE p.quotOrderCycleId IS NULL;
    """)
    op.execute("""
        UPDATE w
        SET w.quotOrderCycleId = c.quotOrderCycleId
        FROM QuotPOWorkingSheet w
        JOIN QuotPurchaseOrder po ON po.quotPOId = w.quotPOId
        JOIN QuotOrderCycle c ON c.quotId = po.quotId AND c.cycleNo = 1
        WHERE w.quotOrderCycleId IS NULL;
    """)
    op.execute("""
        UPDATE v
        SET v.quotOrderCycleId = c.quotOrderCycleId
        FROM QuotViabilitySheet v
        JOIN QuotOrderCycle c ON c.quotId = v.quotId AND c.cycleNo = 1
        WHERE v.quotOrderCycleId IS NULL;
    """)
    op.execute("""
        UPDATE a
        SET a.quotOrderCycleId = c.quotOrderCycleId
        FROM QuotAnnexure a
        JOIN QuotOrderCycle c ON c.quotId = a.quotId AND c.cycleNo = 1
        WHERE a.quotOrderCycleId IS NULL;
    """)

    # ------------------------------------------------------------------
    # 5) Flip the four main child tables' quotOrderCycleId to NOT NULL.
    #    LifecycleUnlockAudit stays nullable — Stage-1 quotation unlocks
    #    don't have a cycle, and legacy audits pre-CR didn't either.
    # ------------------------------------------------------------------
    op.alter_column(
        "QuotPurchaseOrder", "quotOrderCycleId",
        existing_type=sa.Integer, nullable=False,
    )
    op.alter_column(
        "QuotPOWorkingSheet", "quotOrderCycleId",
        existing_type=sa.Integer, nullable=False,
    )
    op.alter_column(
        "QuotViabilitySheet", "quotOrderCycleId",
        existing_type=sa.Integer, nullable=False,
    )
    op.alter_column(
        "QuotAnnexure", "quotOrderCycleId",
        existing_type=sa.Integer, nullable=False,
    )

    # ------------------------------------------------------------------
    # 6) Drop the UNIQUE filtered index that enforced 1 PO per quotation.
    #    With cycles in place, multi-PO is the normal path.
    # ------------------------------------------------------------------
    op.drop_index(
        "UX_QuotPurchaseOrder_quotId_active",
        table_name="QuotPurchaseOrder",
    )

    # Drop the server_default on the new RBAC flags so future inserts
    # have to provide an explicit value (matches the rest of the
    # codebase's RoleMenuMap columns).
    op.alter_column("RoleMenuMap", "CanCaptureLOI", server_default=None)
    op.alter_column("RoleMenuMap", "CanStartNewCycle", server_default=None)


def downgrade() -> None:
    # Reverse-order tear-down. Lossy for cycle data (the cycle rows
    # themselves are dropped) but child-table references restore to
    # the pre-CR state.

    # Recreate the UNIQUE filtered index BEFORE dropping the cycle
    # FKs, else SQL Server may refuse to drop the FK constraint while
    # rows still reference the cycle table.
    op.create_index(
        "UX_QuotPurchaseOrder_quotId_active",
        "QuotPurchaseOrder",
        ["quotId"],
        unique=True,
        mssql_where=sa.text("isActive = 1"),
    )

    op.alter_column("QuotAnnexure", "quotOrderCycleId", existing_type=sa.Integer, nullable=True)
    op.alter_column("QuotViabilitySheet", "quotOrderCycleId", existing_type=sa.Integer, nullable=True)
    op.alter_column("QuotPOWorkingSheet", "quotOrderCycleId", existing_type=sa.Integer, nullable=True)
    op.alter_column("QuotPurchaseOrder", "quotOrderCycleId", existing_type=sa.Integer, nullable=True)

    op.drop_column("LifecycleUnlockAudit", "quotOrderCycleId")
    op.drop_column("QuotAnnexure", "quotOrderCycleId")
    op.drop_column("QuotViabilitySheet", "quotOrderCycleId")
    op.drop_column("QuotPOWorkingSheet", "quotOrderCycleId")
    op.drop_column("QuotPurchaseOrder", "loiSequence")
    op.drop_column("QuotPurchaseOrder", "isLOI")
    op.drop_column("QuotPurchaseOrder", "quotOrderCycleId")

    op.drop_column("RoleMenuMap", "CanStartNewCycle")
    op.drop_column("RoleMenuMap", "CanCaptureLOI")

    op.drop_index("ix_quot_order_cycle_company", table_name="QuotOrderCycle")
    op.drop_index("ix_quot_order_cycle_quot_status", table_name="QuotOrderCycle")
    op.drop_index("uq_quot_order_cycle_quot_cycle_no", table_name="QuotOrderCycle")
    op.drop_table("QuotOrderCycle")
