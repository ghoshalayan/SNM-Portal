from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class ItemGrade(Base, AuditMixin):
    __tablename__ = "ItemGrade"

    itemGradeId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    itemGradeName = Column(String(100), nullable=False)


class ItemName(Base, AuditMixin):
    __tablename__ = "ItemName"

    itemId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    itemGradeId = Column(Integer, ForeignKey("ItemGrade.itemGradeId"), nullable=False)
    itemName = Column(String(100), nullable=False)
    itemDia = Column(String(50), nullable=True)
    itemLength = Column(String(50), nullable=True)
    erpItemCode = Column(String(50), nullable=True)
    erpName = Column(String(100), nullable=True)

    grade = relationship("ItemGrade", foreign_keys=[itemGradeId])


class ItemLength(Base, AuditMixin):
    __tablename__ = "ItemLength"

    itemLengthId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    itemId = Column(Integer, ForeignKey("ItemName.itemId"), nullable=False)
    itemLength = Column(String(50), nullable=False)

    item = relationship("ItemName", foreign_keys=[itemId])


class ItemSize(Base, AuditMixin):
    __tablename__ = "ItemSize"

    itemSizeId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    itemId = Column(Integer, ForeignKey("ItemName.itemId"), nullable=False)
    itemSize = Column(String(50), nullable=False)

    item = relationship("ItemName", foreign_keys=[itemId])
