-- ============================================================================
-- SNM Portal - Full Rollback Script
-- Drops all tables in correct FK dependency order
-- WARNING: This will destroy ALL data. Use only on dev/test environments.
-- ============================================================================

-- TIER 7: Final dependent tables
IF OBJECT_ID('QuotTermsNConditions', 'U') IS NOT NULL DROP TABLE QuotTermsNConditions;
IF OBJECT_ID('QuotDetails', 'U') IS NOT NULL DROP TABLE QuotDetails;
IF OBJECT_ID('CustomerEnquiryCosting', 'U') IS NOT NULL DROP TABLE CustomerEnquiryCosting;
IF OBJECT_ID('Asset', 'U') IS NOT NULL DROP TABLE Asset;

-- TIER 6: Quotation
IF OBJECT_ID('QuotSummary', 'U') IS NOT NULL DROP TABLE QuotSummary;

-- TIER 5: Enquiry
IF OBJECT_ID('CustomerEnquiryDetails', 'U') IS NOT NULL DROP TABLE CustomerEnquiryDetails;
IF OBJECT_ID('CustomerEnquiry', 'U') IS NOT NULL DROP TABLE CustomerEnquiry;

-- TIER 4: Item details, Customer details
IF OBJECT_ID('ItemSize', 'U') IS NOT NULL DROP TABLE ItemSize;
IF OBJECT_ID('ItemLength', 'U') IS NOT NULL DROP TABLE ItemLength;
IF OBJECT_ID('CustomerSite', 'U') IS NOT NULL DROP TABLE CustomerSite;
IF OBJECT_ID('CustomerContacts', 'U') IS NOT NULL DROP TABLE CustomerContacts;

-- TIER 3: Junction / dependent
IF OBJECT_ID('UserRoleMap', 'U') IS NOT NULL DROP TABLE UserRoleMap;
IF OBJECT_ID('RoleMenuMap', 'U') IS NOT NULL DROP TABLE RoleMenuMap;
IF OBJECT_ID('ItemName', 'U') IS NOT NULL DROP TABLE ItemName;
IF OBJECT_ID('CustomerMaster', 'U') IS NOT NULL DROP TABLE CustomerMaster;

-- TIER 2: Company-scoped
IF OBJECT_ID('UserMaster', 'U') IS NOT NULL DROP TABLE UserMaster;
IF OBJECT_ID('MenuMaster', 'U') IS NOT NULL DROP TABLE MenuMaster;
IF OBJECT_ID('TermsNConditionMaster', 'U') IS NOT NULL DROP TABLE TermsNConditionMaster;
IF OBJECT_ID('RoleMaster', 'U') IS NOT NULL DROP TABLE RoleMaster;
IF OBJECT_ID('RawMaterialCost', 'U') IS NOT NULL DROP TABLE RawMaterialCost;
IF OBJECT_ID('ItemGrade', 'U') IS NOT NULL DROP TABLE ItemGrade;
IF OBJECT_ID('DeliveryTerm', 'U') IS NOT NULL DROP TABLE DeliveryTerm;
IF OBJECT_ID('DeliveryMode', 'U') IS NOT NULL DROP TABLE DeliveryMode;
IF OBJECT_ID('CustomerClassification', 'U') IS NOT NULL DROP TABLE CustomerClassification;
IF OBJECT_ID('CostPointMaster', 'U') IS NOT NULL DROP TABLE CostPointMaster;
IF OBJECT_ID('ContactType', 'U') IS NOT NULL DROP TABLE ContactType;

-- TIER 1: Root
IF OBJECT_ID('Company', 'U') IS NOT NULL DROP TABLE Company;

-- Alembic tracking
IF OBJECT_ID('alembic_version', 'U') IS NOT NULL DROP TABLE alembic_version;
