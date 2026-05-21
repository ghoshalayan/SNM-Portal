"""Approval-time snapshots for viability + annexure.

Soft-flow design (see issues.md and the design discussion 2026-05-20+):
edits to a viability or annexure remain allowed after Approve — the
status flips to ``Approved`` but the row is *not* locked. That trades
the "locked = canonical" guarantee for a snapshot-based one: at the
instant Approve fires we freeze the entire row (plus children, where
applicable) into a snapshot table.

The snapshot is the authoritative "what was approved" answer for
audit, customer dispute, and regulatory questions. Subsequent edits
to the head row are journaled separately via ``log_action`` with an
``"edited after approval"`` marker.

Tables:

  * ``QuotViabilityApprovalSnapshot`` — one row per Approve action on
    a ``QuotViabilitySheet``. ``snapshotData`` holds the full sheet
    columns + every ``QuotViabilityLine`` row as a JSON document.

  * ``QuotAnnexureApprovalSnapshot`` — same shape for ``QuotAnnexure``.
    Annexure has no child table (``diawiseBreakup`` is already an
    in-row JSON column) so the snapshot is just the row itself.

Both tables are append-only by convention; there is no UPDATE/DELETE
path. Re-approval after edits creates a new snapshot row — the chain
of snapshots IS the approval history.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.mssql import NVARCHAR
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import AuditMixin


class QuotViabilityApprovalSnapshot(Base, AuditMixin):
    """Frozen state of a viability sheet at the instant of approval.

    ``snapshotData`` carries the full sheet header + all line rows as a
    single JSON document. Storing as one blob (vs. mirror tables) keeps
    the migration tiny and the read path is a single row lookup — the
    typical query is "show me the approved version", not "report across
    historical line items".
    """
    __tablename__ = "QuotViabilityApprovalSnapshot"

    snapshotId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(
        Integer, ForeignKey("Company.companyId"), nullable=False,
    )
    # Parent sheet. No CASCADE — even if the head sheet is soft-deleted,
    # the historical snapshot must survive (it's the audit answer).
    viabilityId = Column(
        Integer, ForeignKey("QuotViabilitySheet.viabilityId"), nullable=False,
    )
    quotId = Column(
        Integer, ForeignKey("QuotSummary.quotId"), nullable=False,
    )
    # Sheet's version at the time of approval; lets the dropdown render
    # "Approved snapshot of v3" without re-reading the sheet.
    versionNo = Column(Integer, nullable=False)
    # SHA-256 hex of the canonical-JSON content. Used for the D3 short-
    # circuit (no-op re-approval doesn't grow the chain). Nullable for
    # backwards-compat with rows written before migration e2f3g4h5i6j7.
    contentHash = Column(String(64), nullable=True)

    # Who signed it off + when. Independent copy of approvedby /
    # approvedon on the head — those can drift if the head is re-approved
    # under the soft model, but the snapshot's value is frozen.
    approvedByUserId = Column(
        Integer, ForeignKey("UserMaster.userId"), nullable=True,
    )
    approvedByName = Column(String(200), nullable=True)
    approvedAt = Column(DateTime, nullable=False)

    # JSON document — sheet columns + lines[]. ``NVARCHAR(MAX)`` is the
    # SQL Server idiom for "unbounded string"; SQLAlchemy maps it
    # correctly via the mssql dialect.
    snapshotData = Column(NVARCHAR(None), nullable=False)

    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    sheet = relationship("QuotViabilitySheet", foreign_keys=[viabilityId])
    approved_by_user = relationship("User", foreign_keys=[approvedByUserId])


class QuotFWSApprovalSnapshot(Base, AuditMixin):
    """Frozen state of a cycle's Final Working Sheet at the instant of approval.

    Unlike viability and annexure, the FWS has no parent header row —
    it's a flat collection of ``QuotPOWorkingSheet`` line rows scoped to
    a cycle. The snapshot therefore captures the entire collection as a
    JSON document; ``versionNo`` is per-cycle (each cycle has its own
    independent counter starting at 1).

    Snapshot rows are append-only. Re-approval where the content is
    identical to the latest snapshot is short-circuited at the service
    layer (D3 — audit-only event, no new snapshot row).
    """
    __tablename__ = "QuotFWSApprovalSnapshot"

    snapshotId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(
        Integer, ForeignKey("Company.companyId"), nullable=False,
    )
    # FWS lives at the cycle level — there is no single parent table
    # to point at, so we anchor the snapshot to the cycle directly.
    quotOrderCycleId = Column(
        Integer, ForeignKey("QuotOrderCycle.quotOrderCycleId"), nullable=False,
    )
    quotId = Column(
        Integer, ForeignKey("QuotSummary.quotId"), nullable=False,
    )
    # Per-cycle counter. Cycle 1 starts at 1; cycle 2 also starts at 1.
    # Display label is composed as ``C{cycleNo}-V{versionNo}`` on the FE.
    versionNo = Column(Integer, nullable=False)
    # SHA-256 of the canonical JSON content (used to detect "no-change"
    # re-approvals so we don't grow duplicate-content snapshots).
    contentHash = Column(String(64), nullable=False)

    approvedByUserId = Column(
        Integer, ForeignKey("UserMaster.userId"), nullable=True,
    )
    approvedByName = Column(String(200), nullable=True)
    approvedAt = Column(DateTime, nullable=False)

    # JSON: list of all active line rows for the cycle at approval time.
    snapshotData = Column(NVARCHAR(None), nullable=False)

    cycle = relationship("QuotOrderCycle", foreign_keys=[quotOrderCycleId])
    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    approved_by_user = relationship("User", foreign_keys=[approvedByUserId])


class QuotAnnexureApprovalSnapshot(Base, AuditMixin):
    """Frozen state of an annexure at the instant of approval.

    Annexure has no child table — ``diawiseBreakup`` is already an
    in-row JSON column. The snapshot just captures the parent row's
    columns as JSON.
    """
    __tablename__ = "QuotAnnexureApprovalSnapshot"

    snapshotId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(
        Integer, ForeignKey("Company.companyId"), nullable=False,
    )
    annexureId = Column(
        Integer, ForeignKey("QuotAnnexure.annexureId"), nullable=False,
    )
    quotId = Column(
        Integer, ForeignKey("QuotSummary.quotId"), nullable=False,
    )
    versionNo = Column(Integer, nullable=False)
    # See QuotViabilityApprovalSnapshot.contentHash — same shape, same
    # nullable-for-backcompat semantics.
    contentHash = Column(String(64), nullable=True)

    approvedByUserId = Column(
        Integer, ForeignKey("UserMaster.userId"), nullable=True,
    )
    approvedByName = Column(String(200), nullable=True)
    approvedAt = Column(DateTime, nullable=False)

    snapshotData = Column(NVARCHAR(None), nullable=False)

    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    annexure = relationship("QuotAnnexure", foreign_keys=[annexureId])
    approved_by_user = relationship("User", foreign_keys=[approvedByUserId])
