from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.database import Base
from app.models.base import AuditMixin


class Company(Base, AuditMixin):
    __tablename__ = "Company"

    companyId = Column(Integer, primary_key=True, autoincrement=True)
    companyName = Column(String(100), nullable=False)
    companyCode = Column(String(50), nullable=True)
    address = Column(String(500), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    pinCode = Column(String(20), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    website = Column(String(200), nullable=True)
    GSTN = Column(String(50), nullable=True)
    PAN = Column(String(50), nullable=True)
    logoUrl = Column(String(500), nullable=True)

    # Optional SMTP/Email Configuration
    MailFrom = Column(String(100), nullable=True)
    MailPassword = Column(String(200), nullable=True)
    SMTP = Column(String(100), nullable=True)
    PortNo = Column(String(10), nullable=True)
