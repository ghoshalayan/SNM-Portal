from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from app.core.database import Base
from app.models.base import AuditMixin


class Country(Base, AuditMixin):
    __tablename__ = "Country"

    countryid = Column(Integer, primary_key=True, autoincrement=True)
    countryname = Column(String(50), nullable=False)


class StateMaster(Base, AuditMixin):
    __tablename__ = "StateMaster"

    stateid = Column(Integer, primary_key=True, autoincrement=True)
    StateName = Column(String(50), nullable=False)
    Country = Column(String(50), nullable=True)


class DistrictMaster(Base, AuditMixin):
    __tablename__ = "DistrictMaster"

    districtid = Column(Integer, primary_key=True, autoincrement=True)
    districName = Column(String(50), nullable=False)
    StateName = Column(String(50), nullable=True)
    Country = Column(String(50), nullable=True)
