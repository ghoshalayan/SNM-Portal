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
    # Per-PO scoping (LOI / Cycle CR follow-up). When a file is dropped
    # against a specific PO / LOI row inside a cycle, the upload writes
    # this FK so the attachments panel can scope to the active picker
    # selection. NULL keeps legacy quotation-scoped uploads working —
    # an asset with quotId set + quotPOId NULL is "quotation-level".
    quotPOId = Column(
        Integer, ForeignKey("QuotPurchaseOrder.quotPOId"), nullable=True,
    )
