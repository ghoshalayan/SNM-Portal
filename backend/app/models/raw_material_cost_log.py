from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.timezone import now_ist


class RawMaterialCostLog(Base):
    """Append-only audit log for Raw Material Cost updates.

    One row per UPDATE (and optionally CREATE) of RawMaterialCost.
    Stores old/new values and timestamp in IST.
    """
    __tablename__ = "RawMaterialCostLog"

    logId = Column(Integer, primary_key=True, autoincrement=True)
    rawMaterialCostId = Column(
        Integer, ForeignKey("RawMaterialCost.rawMaterialCostId"), nullable=False
    )
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    dia = Column(String(50), nullable=False)
    oldCost = Column(Numeric(18, 2), nullable=True)
    newCost = Column(Numeric(18, 2), nullable=False)
    oldEffectedFrom = Column(DateTime, nullable=True)
    newEffectedFrom = Column(DateTime, nullable=True)
    action = Column(String(20), nullable=False, default="UPDATE")  # CREATE | UPDATE
    remarks = Column(String(500), nullable=True)
    changedBy = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    changedOn = Column(DateTime, default=now_ist, nullable=False)

    raw_material_cost = relationship("RawMaterialCost", foreign_keys=[rawMaterialCostId])
    changed_by_user = relationship("User", foreign_keys=[changedBy])
