from sqlalchemy import Column, Integer, String, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class Asset(Base, AuditMixin):
    __tablename__ = "Asset"

    assetId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    enqid = Column(Integer, ForeignKey("CustomerEnquiry.enqid"), nullable=True)
    quotId = Column(Integer, ForeignKey("QuotSummary.quotId"), nullable=True)
    assetName = Column(String(200), nullable=True)
    fileName = Column(String(200), nullable=False)
    fileUrl = Column(String(500), nullable=False)
    fileType = Column(String(50), nullable=True)
    fileSize = Column(Integer, nullable=True)
    category = Column(String(30), nullable=True)  # 'general' (default) | 'po_document' | ...
