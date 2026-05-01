from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import AuditMixin


class CustomerMaster(Base, AuditMixin):
    __tablename__ = "CustomerMaster"

    customerId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    classificationId = Column(Integer, ForeignKey("CustomerClassification.classificationId"), nullable=True)
    customerCode = Column(String(50), nullable=True)
    customerName = Column(String(200), nullable=False)
    GSTN = Column(String(50), nullable=True)
    PAN = Column(String(50), nullable=True)
    siteId = Column(Integer, nullable=True)
    # RBAC v2: owner tracking (nullable for backward compat; customers are still
    # company-wide visible per business rule, owner used for audit/reporting)
    ownerUserId = Column(Integer, ForeignKey("UserMaster.userId"), nullable=True)
    ownerRoleId = Column(Integer, ForeignKey("RoleMaster.roleId"), nullable=True)

    classification = relationship("CustomerClassification", foreign_keys=[classificationId])
    contacts = relationship("CustomerContacts", back_populates="customer")
    sites = relationship("CustomerSite", back_populates="customer")


class CustomerContacts(Base, AuditMixin):
    __tablename__ = "CustomerContacts"

    customerContactId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    customerId = Column(Integer, ForeignKey("CustomerMaster.customerId"), nullable=False)
    contactTypeId = Column(Integer, ForeignKey("ContactType.contactTypeId"), nullable=True)
    contactPersonName = Column(String(100), nullable=True)
    designation = Column(String(100), nullable=True)
    personalPhone = Column(String(20), nullable=True)
    personalEmail = Column(String(100), nullable=True)
    officePhone = Column(String(20), nullable=True)
    officeEmail = Column(String(100), nullable=True)
    address = Column(String(500), nullable=True)
    state = Column(String(100), nullable=True)
    dist = Column(String(100), nullable=True)
    birthday = Column(Date, nullable=True)
    anniversary = Column(Date, nullable=True)

    customer = relationship("CustomerMaster", back_populates="contacts")
    contact_type = relationship("ContactType", foreign_keys=[contactTypeId])


class CustomerSite(Base, AuditMixin):
    __tablename__ = "CustomerSite"

    siteId = Column(Integer, primary_key=True, autoincrement=True)
    companyId = Column(Integer, ForeignKey("Company.companyId"), nullable=False)
    customerId = Column(Integer, ForeignKey("CustomerMaster.customerId"), nullable=False)
    siteAddressCode = Column(String(50), nullable=True)
    addressLine = Column(String(500), nullable=True)
    state = Column(String(100), nullable=True)
    dist = Column(String(100), nullable=True)
    PIN = Column(String(20), nullable=True)
    contactPerson1 = Column(String(100), nullable=True)
    contactPhone1 = Column(String(20), nullable=True)
    contactEmail1 = Column(String(100), nullable=True)
    contactPerson2 = Column(String(100), nullable=True)
    contactPhone2 = Column(String(20), nullable=True)
    contactEmail2 = Column(String(100), nullable=True)
    contactPerson3 = Column(String(100), nullable=True)
    contactPhone3 = Column(String(20), nullable=True)
    contactEmail3 = Column(String(100), nullable=True)
    isHeadOffice = Column(Boolean, default=False, nullable=False)

    customer = relationship("CustomerMaster", back_populates="sites")
