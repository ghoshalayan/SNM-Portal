"""QuotOrderCycle — the call-off / cycle grouping under a quotation.

Introduced by the LOI/Cycle CR (see `MultiplePO-LOI-Cycle-CR.md`). One
quotation can spawn N cycles; each cycle bundles its own working sheet,
viability sheet, annexure, and a collection of LOIs + POs. Cycle 2+
inherit rates from the previous cycle's approved viability so the
quotation "circulates" without re-quoting.

Status state machine:
    Active   → Complete    (annexure approved + ≥1 PO captured + explicit close)
    Active   → Abandoned   (explicit user action)

The parent quotation's status stays at Stage 1 (`Converted` means
"≥ 1 cycle has been started"); the cycle's own status is the real
position past Stage 1.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import AuditMixin


class QuotOrderCycle(Base, AuditMixin):
    """One row per call-off cycle. ``cycleNo`` is sequential per
    quotation (1, 2, 3 …); ``parentCycleId`` captures rate-inheritance
    lineage (cycle 2 inherits from cycle 1, cycle 3 from cycle 2, etc.).
    NULL ``parentCycleId`` on cycle 1 of a quotation.
    """

    __tablename__ = "QuotOrderCycle"

    quotOrderCycleId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(
        Integer, ForeignKey("Company.companyId"), nullable=False,
    )
    quotId = Column(
        Integer, ForeignKey("QuotSummary.quotId"), nullable=False,
    )
    cycleNo = Column(Integer, nullable=False)
    # ``Active`` | ``Complete`` | ``Abandoned`` — see module docstring.
    status = Column(String(20), default="Active", nullable=False)

    parentCycleId = Column(
        Integer,
        ForeignKey("QuotOrderCycle.quotOrderCycleId"),
        nullable=True,
    )

    startedOn = Column(DateTime, nullable=False)
    startedBy = Column(
        Integer, ForeignKey("UserMaster.userId"), nullable=False,
    )
    closedOn = Column(DateTime, nullable=True)
    closedBy = Column(
        Integer, ForeignKey("UserMaster.userId"), nullable=True,
    )
    notes = Column(String(500), nullable=True)

    # ---- relationships ----
    quotation = relationship("QuotSummary", foreign_keys=[quotId])
    parent_cycle = relationship(
        "QuotOrderCycle", remote_side=[quotOrderCycleId],
    )
    started_by_user = relationship("User", foreign_keys=[startedBy])
    closed_by_user = relationship("User", foreign_keys=[closedBy])

    # Indexes (incl. the filtered UNIQUE on (quotId, cycleNo)) live in
    # the Phase 1A migration ``z7a8b9c0d1e2_phase1a_loi_cycle_data_model.py``.
    # Keeping them out of ``__table_args__`` matches the rest of the
    # codebase and avoids the sqlite-dialect quirk where ``where=``
    # expects a SQL expression rather than a raw string literal — which
    # blocks in-memory test DBs from spinning up the schema.
