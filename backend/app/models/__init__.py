# Import all models so Alembic can detect them
from app.models.company import Company
from app.models.user import User, UserRoleMap
from app.models.role import Role
from app.models.menu import MenuMaster
from app.models.role_menu_map import RoleMenuMap
from app.models.item import ItemGrade, ItemName, ItemLength, ItemSize
from app.models.delivery import DeliveryTerm, DeliveryMode
from app.models.customer_classification import CustomerClassification
from app.models.contact_type import ContactType
from app.models.cost_point import CostPointMaster
from app.models.customer import CustomerMaster, CustomerContacts, CustomerSite
from app.models.enquiry import CustomerEnquiry, CustomerEnquiryDetails, CustomerEnquiryCosting, CustomerEnqFollowUp
from app.models.quotation import QuotSummary, QuotDetails, QuotTermsNConditions
from app.models.terms_condition import TermsNConditionMaster
from app.models.raw_material_cost import RawMaterialCost
from app.models.asset import Asset
from app.models.location import Country, StateMaster, DistrictMaster
from app.models.dia import DiaMaster
from app.models.status import EnQStatusMaster, QuotQStatusMaster
from app.models.communication import CommunicationMode, CommunicationLog
from app.models.quotation_format import QuotationFormat
from app.models.financial_year import FinancialYear
from app.models.ownership_transfer import OwnershipTransfer
from app.models.cost_template import CostTemplate
from app.models.quot_viability import QuotViabilitySheet, QuotViabilityLine
from app.models.quot_purchase_order import QuotPurchaseOrder
from app.models.quot_po_working_sheet import QuotPOWorkingSheet
from app.models.quot_annexure import QuotAnnexure
from app.models.role_menu_audit import RoleMenuMapAudit
from app.models.quot_activity_log import QuotActivityLog
from app.models.lifecycle_unlock_audit import LifecycleUnlockAudit

__all__ = [
    "Company",
    "User", "UserRoleMap",
    "Role",
    "MenuMaster",
    "RoleMenuMap",
    "ItemGrade", "ItemName", "ItemLength", "ItemSize",
    "DeliveryTerm", "DeliveryMode",
    "CustomerClassification",
    "ContactType",
    "CostPointMaster",
    "CustomerMaster", "CustomerContacts", "CustomerSite",
    "CustomerEnquiry", "CustomerEnquiryDetails", "CustomerEnquiryCosting", "CustomerEnqFollowUp",
    "QuotSummary", "QuotDetails", "QuotTermsNConditions",
    "TermsNConditionMaster",
    "RawMaterialCost",
    "Asset",
    "Country", "StateMaster", "DistrictMaster",
    "DiaMaster",
    "EnQStatusMaster", "QuotQStatusMaster",
    "CommunicationMode", "CommunicationLog",
    "QuotationFormat",
    "FinancialYear",
    "OwnershipTransfer",
    "CostTemplate",
    "QuotViabilitySheet", "QuotViabilityLine",
    "QuotPurchaseOrder",
    "QuotPOWorkingSheet",
    "QuotAnnexure",
    "RoleMenuMapAudit",
    "QuotActivityLog",
    "LifecycleUnlockAudit",
]
