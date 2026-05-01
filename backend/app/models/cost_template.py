from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class CostTemplate(Base, AuditMixin):
    __tablename__ = "CostTemplate"

    templateId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    templateName = Column(String(200), nullable=False)

    Marketing = Column(Numeric(18, 2), nullable=True)
    FreightTrailer = Column(Numeric(18, 2), nullable=True)
    FreightTruck = Column(Numeric(18, 2), nullable=True)
    Unloading = Column(Numeric(18, 2), nullable=True)
    OHD = Column(Numeric(18, 2), nullable=True)
    IFC = Column(Numeric(18, 2), nullable=True)
    WeighmentDiff = Column(Numeric(18, 2), nullable=True)
    CD = Column(Numeric(18, 2), nullable=True)
    SWECharge = Column(Numeric(18, 2), nullable=True)
    CRS = Column(Numeric(18, 2), nullable=True)
    IncCharge = Column(Numeric(18, 2), nullable=True)
    ShortLnthCharge = Column(Numeric(18, 2), nullable=True)
    SpeciFicLnthCharge = Column(Numeric(18, 2), nullable=True)
    ExtraCharge = Column(Numeric(18, 2), nullable=True)
    Fluctuation = Column(Numeric(18, 2), nullable=True)
    Commission = Column(Numeric(18, 2), nullable=True)
    Misc = Column(Numeric(18, 2), nullable=True)
    Testing = Column(Numeric(18, 2), nullable=True)
    MOUTOD = Column(Numeric(18, 2), nullable=True)
    SplDisc = Column(Numeric(18, 2), nullable=True)
    JC = Column(Numeric(18, 2), nullable=True)
