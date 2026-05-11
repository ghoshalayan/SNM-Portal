from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class QuotationFormat(Base, AuditMixin):
    __tablename__ = "QuotationFormat"

    qfId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    formatName = Column(String(200), nullable=False)
    qHeader = Column(String, nullable=True)
    qContent = Column(String, nullable=True)
    qFooter = Column(String, nullable=True)
    isCurrent = Column(Boolean, default=False, nullable=False)

    # Print styling — per-format presentation overrides applied by the
    # quotation print component to both the inline default table and the
    # format-substituted programmatic table. All nullable so the print
    # component can fall back to hardcoded defaults if a value is NULL,
    # but the migration backfills sensible defaults so existing rows
    # render the same way new ones do.
    headerBgColor = Column(String(50), nullable=True)        # e.g. "#1565c0" or "saffron"
    headerTextColor = Column(String(50), nullable=True)      # e.g. "#FFFFFF"
    roundingMode = Column(String(10), nullable=True)         # ceiling | floor | round
    amountDecimals = Column(Integer, nullable=True)          # 0-2
    taxDecimals = Column(Integer, nullable=True)             # 0-2
    taxShowPercent = Column(Boolean, nullable=True)
    qtyDecimals = Column(Integer, nullable=True)             # 0-3
    dimensionDecimals = Column(Integer, nullable=True)       # 0-1
    columnAlignments = Column(String, nullable=True)         # JSON: { col: { header, body } }

    company = relationship("Company", foreign_keys=[companyId])
