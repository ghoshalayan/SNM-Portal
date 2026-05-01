"""Performance indexes for production scale (5k-50k rows)

Phase 1 of pagination/performance overhaul. Adds indexes that benefit
every single query already in the codebase — no code changes required.

Indexes are designed around the F1 Company + F5 Hierarchy + F6 Location
filter pipeline. Each index supports the exact WHERE pattern used by
apply_company_filter / apply_hierarchy_filter / apply_location_filter.

Indexes use SQL Server's filtered index syntax to skip soft-deleted rows
for maximum selectivity.

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-04-20
"""
from typing import Sequence, Union
from alembic import op

revision: str = "n8o9p0q1r2s3"
down_revision: Union[str, None] = "m7n8o9p0q1r2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEXES = [
    # ------------------------------------------------------------------
    # CustomerMaster — searched by name/code, filtered by company + owner
    # ------------------------------------------------------------------
    ("IX_Customer_Company_Active_Name",
     "CustomerMaster", "(companyId, customerName)",
     "WHERE isActive = 1"),
    ("IX_Customer_Company_Active_Code",
     "CustomerMaster", "(companyId, customerCode)",
     "WHERE isActive = 1 AND customerCode IS NOT NULL"),
    ("IX_Customer_Company_Owner",
     "CustomerMaster", "(companyId, ownerUserId)",
     "WHERE isActive = 1"),

    # ------------------------------------------------------------------
    # CustomerContacts — F6 location filter + parent lookup
    # ------------------------------------------------------------------
    ("IX_Contact_Customer",
     "CustomerContacts", "(customerId, companyId)",
     "WHERE isActive = 1"),
    ("IX_Contact_Company_State_Dist",
     "CustomerContacts", "(companyId, state, dist)",
     "WHERE isActive = 1"),

    # ------------------------------------------------------------------
    # CustomerSite — same as contacts + HO lookups
    # ------------------------------------------------------------------
    ("IX_Site_Customer",
     "CustomerSite", "(customerId, companyId)",
     "WHERE isActive = 1"),
    ("IX_Site_Company_State_Dist",
     "CustomerSite", "(companyId, state, dist)",
     "WHERE isActive = 1"),
    ("IX_Site_Customer_HO",
     "CustomerSite", "(customerId, isHeadOffice)",
     "WHERE isActive = 1 AND isHeadOffice = 1"),

    # ------------------------------------------------------------------
    # CustomerEnquiry — the main hot path (list, search, visibility)
    # ------------------------------------------------------------------
    ("IX_Enquiry_Company_Active_EnqNo",
     "CustomerEnquiry", "(companyId, enqNo)",
     "WHERE isActive = 1"),
    ("IX_Enquiry_Company_Owner_Date",
     "CustomerEnquiry", "(companyId, ownerUserId, enqDate DESC)",
     "WHERE isActive = 1"),
    ("IX_Enquiry_Company_Customer",
     "CustomerEnquiry", "(companyId, customerId)",
     "WHERE isActive = 1"),
    ("IX_Enquiry_Company_Status_Date",
     "CustomerEnquiry", "(companyId, status, enqDate DESC)",
     "WHERE isActive = 1"),

    # Sub-resources of enquiry
    ("IX_EnquiryDetails_Enquiry",
     "CustomerEnquiryDetails", "(enqid, companyId)",
     "WHERE isActive = 1"),
    ("IX_EnquiryCosting_Enquiry_Version",
     "CustomerEnquiryCosting", "(enqid, versionNo DESC)",
     "WHERE isActive = 1"),
    ("IX_EnqFollowUp_Enquiry",
     "CustomerEnqFollowUp", "(enqid, companyId)",
     "WHERE isActive = 1"),

    # ------------------------------------------------------------------
    # QuotSummary — same pattern as enquiries
    # ------------------------------------------------------------------
    ("IX_Quot_Company_Active_QuotNo",
     "QuotSummary", "(companyId, quotNo)",
     "WHERE isActive = 1"),
    ("IX_Quot_Company_Owner_Date",
     "QuotSummary", "(companyId, ownerUserId, quotDate DESC)",
     "WHERE isActive = 1"),
    ("IX_Quot_Company_Customer",
     "QuotSummary", "(companyId, customerId)",
     "WHERE isActive = 1"),
    ("IX_Quot_Company_Status",
     "QuotSummary", "(companyId, status)",
     "WHERE isActive = 1"),
    ("IX_Quot_Parent",
     "QuotSummary", "(parentQuotId, versionNo DESC)",
     "WHERE isActive = 1 AND parentQuotId IS NOT NULL"),

    # Quotation sub-resources
    ("IX_QuotDetails_Quot",
     "QuotDetails", "(quotId)",
     "WHERE isActive = 1"),
    ("IX_QuotTnC_Quot_Order",
     "QuotTermsNConditions", "(quotId, sortOrder)",
     "WHERE isActive = 1"),
    ("IX_QuotTnC_Master",
     "QuotTermsNConditions", "(quotId, masterTncId)",
     "WHERE isActive = 1 AND masterTncId IS NOT NULL"),

    # ------------------------------------------------------------------
    # User / UserRoleMap — hot path for visibility BFS + login
    # ------------------------------------------------------------------
    ("IX_User_Company_Active_Name",
     "UserMaster", "(companyId, userName)",
     "WHERE isActive = 1"),
    ("IX_User_Login",
     "UserMaster", "(userLogin)",
     "WHERE isActive = 1"),

    ("IX_UserRoleMap_Company_Active",
     "UserRoleMap", "(companyId, userId)",
     "WHERE isActive = 1"),
    ("IX_UserRoleMap_ReportTo",
     "UserRoleMap", "(companyId, reportTo)",
     "WHERE isActive = 1 AND reportTo IS NOT NULL"),

    ("IX_UserLocationMap_User",
     "UserLocationMap", "(userId, companyId)",
     "WHERE isActive = 1"),

    # ------------------------------------------------------------------
    # Communication Logs — large volume over time
    # ------------------------------------------------------------------
    ("IX_CommLog_Company_Owner_Date",
     "CommunicationLog", "(companyId, ownerUserId, commlogID DESC)",
     "WHERE isActive = 1"),
    ("IX_CommLog_Enquiry",
     "CommunicationLog", "(enqid)",
     "WHERE isActive = 1 AND enqid IS NOT NULL"),
    ("IX_CommLog_Quotation",
     "CommunicationLog", "(quoteid)",
     "WHERE isActive = 1 AND quoteid IS NOT NULL"),

    # ------------------------------------------------------------------
    # Asset — filtered by enquiry/quotation ownership
    # ------------------------------------------------------------------
    ("IX_Asset_Company_Enquiry",
     "Asset", "(companyId, enqid)",
     "WHERE isActive = 1 AND enqid IS NOT NULL"),
    ("IX_Asset_Company_Quotation",
     "Asset", "(companyId, quotId)",
     "WHERE isActive = 1 AND quotId IS NOT NULL"),

    # ------------------------------------------------------------------
    # RoleMenuMap — permission lookup on every API call
    # ------------------------------------------------------------------
    ("IX_RoleMenuMap_Role",
     "RoleMenuMap", "(roleId, menuId)",
     "WHERE isActive = 1"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for name, table, cols, where in INDEXES:
        # SQL Server: create only if not exists; filtered indexes for soft-delete skip
        sql = f"""
        IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{name}' AND object_id = OBJECT_ID('{table}'))
        BEGIN
            CREATE NONCLUSTERED INDEX {name}
            ON {table} {cols}
            {where};
        END
        """
        bind.exec_driver_sql(sql)


def downgrade() -> None:
    bind = op.get_bind()
    for name, table, _cols, _where in INDEXES:
        sql = f"""
        IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = '{name}' AND object_id = OBJECT_ID('{table}'))
        BEGIN
            DROP INDEX {name} ON {table};
        END
        """
        bind.exec_driver_sql(sql)
