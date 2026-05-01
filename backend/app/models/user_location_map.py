from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class UserLocationMap(Base, AuditMixin):
    __tablename__ = "UserLocationMap"

    userLocationMapId = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=False)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    countryid = Column(Integer, ForeignKey("Country.countryid"), nullable=False)
    stateid = Column(Integer, ForeignKey("StateMaster.stateid"), nullable=False)
    districtid = Column(Integer, ForeignKey("DistrictMaster.districtid"), nullable=True)

    user = relationship("User", foreign_keys=[userId])
    company = relationship("Company", foreign_keys=[companyId])
    country = relationship("Country", foreign_keys=[countryid])
    state = relationship("StateMaster", foreign_keys=[stateid])
    district = relationship("DistrictMaster", foreign_keys=[districtid])
