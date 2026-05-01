from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class DiaMaster(Base, AuditMixin):
    __tablename__ = "DiaMaster"

    diaid = Column(Integer, primary_key=True, autoincrement=True)
    itemid = Column(Integer, ForeignKey("ItemName.itemId"), nullable=False)
    diadescription = Column(String(50), nullable=False)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)

    item = relationship("ItemName", foreign_keys=[itemid])
