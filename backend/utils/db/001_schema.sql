-- ============================================================================
-- SNM Portal - Database Schema (SQL Server)
-- Generated from Alembic migration: 9eaf9699f05f
-- All 27 tables (25 models + alembic_version tracking)
-- ============================================================================

-- ============================================================================
-- TIER 1: Independent / Root Tables (no FKs to other app tables)
-- ============================================================================

CREATE TABLE Company (
    companyId       INT IDENTITY(1,1) PRIMARY KEY,
    companyName     NVARCHAR(100) NOT NULL,
    companyCode     NVARCHAR(50)  NULL,
    address         NVARCHAR(500) NULL,
    city            NVARCHAR(100) NULL,
    state           NVARCHAR(100) NULL,
    country         NVARCHAR(100) NULL,
    pinCode         NVARCHAR(20)  NULL,
    phone           NVARCHAR(20)  NULL,
    email           NVARCHAR(100) NULL,
    website         NVARCHAR(200) NULL,
    GSTN            NVARCHAR(50)  NULL,
    PAN             NVARCHAR(50)  NULL,
    logoUrl         NVARCHAR(500) NULL,
    -- SMTP / Email config (optional, per-company)
    MailFrom        NVARCHAR(100) NULL,
    MailPassword    NVARCHAR(200) NULL,
    SMTP            NVARCHAR(100) NULL,
    PortNo          NVARCHAR(10)  NULL,
    -- Audit
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- ============================================================================
-- TIER 2: Tables with FK to Company only
-- ============================================================================

CREATE TABLE ContactType (
    contactTypeId   INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    contactType     NVARCHAR(100) NOT NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE CostPointMaster (
    costPointId     INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    costPointName   NVARCHAR(100) NOT NULL,
    isPrimary       BIT           NOT NULL DEFAULT 0,
    isTax           BIT           NOT NULL DEFAULT 0,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE CustomerClassification (
    classificationId INT IDENTITY(1,1) PRIMARY KEY,
    companyId        INT           NOT NULL REFERENCES Company(companyId),
    classificationName NVARCHAR(100) NOT NULL,
    createdon        DATETIME      NULL,
    createdby        INT           NULL,
    lastupdateon     DATETIME      NULL,
    lastupdateby     INT           NULL,
    isActive         BIT           NOT NULL DEFAULT 1
);

CREATE TABLE DeliveryMode (
    deliveryModeId  INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    deliveryMode    NVARCHAR(200) NOT NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE DeliveryTerm (
    deliveryTermId  INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    deliveryTerm    NVARCHAR(200) NOT NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE ItemGrade (
    itemGradeId     INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    itemGradeName   NVARCHAR(100) NOT NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE RawMaterialCost (
    rawMaterialCostId INT IDENTITY(1,1) PRIMARY KEY,
    companyId         INT            NOT NULL REFERENCES Company(companyId),
    dia               NVARCHAR(50)   NOT NULL,
    tpcost            DECIMAL(18,2)  NOT NULL,
    effectedFrom      DATETIME       NULL,
    createdon         DATETIME       NULL,
    createdby         INT            NULL,
    lastupdateon      DATETIME       NULL,
    lastupdateby      INT            NULL,
    isActive          BIT            NOT NULL DEFAULT 1
);

CREATE TABLE RoleMaster (
    roleId          INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    roleName        NVARCHAR(100) NOT NULL,
    IsSuperAdmin    BIT           NOT NULL DEFAULT 0,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE TermsNConditionMaster (
    tncId           INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    tncName         NVARCHAR(200) NOT NULL,
    tncDescription  NVARCHAR(500) NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- Self-referencing menu tree
CREATE TABLE MenuMaster (
    menuId          INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    menuName        NVARCHAR(100) NOT NULL,
    menuUrl         NVARCHAR(200) NULL,
    menuIcon        NVARCHAR(100) NULL,
    parentMenuId    INT           NULL REFERENCES MenuMaster(menuId),
    menuOrder       INT           NOT NULL DEFAULT 0,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- Self-referencing user hierarchy
CREATE TABLE UserMaster (
    userId          INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    userName        NVARCHAR(100) NOT NULL,
    userCode        NVARCHAR(50)  NULL,
    userEmail       NVARCHAR(100) NULL,
    userPhone       NVARCHAR(20)  NULL,
    userLogin       NVARCHAR(50)  NOT NULL UNIQUE,
    userPassword    NVARCHAR(255) NOT NULL,  -- bcrypt hash
    reportTo        INT           NULL REFERENCES UserMaster(userId),
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- ============================================================================
-- TIER 3: Tables with FKs to Tier 1-2
-- ============================================================================

CREATE TABLE RoleMenuMap (
    roleMenuMapId   INT IDENTITY(1,1) PRIMARY KEY,
    roleId          INT NOT NULL REFERENCES RoleMaster(roleId),
    menuId          INT NOT NULL REFERENCES MenuMaster(menuId),
    CanAdd          BIT NOT NULL DEFAULT 0,
    CanRead         BIT NOT NULL DEFAULT 0,
    CanEdit         BIT NOT NULL DEFAULT 0,
    CanDelete       BIT NOT NULL DEFAULT 0,
    createdon       DATETIME NULL,
    createdby       INT      NULL,
    lastupdateon    DATETIME NULL,
    lastupdateby    INT      NULL,
    isActive        BIT      NOT NULL DEFAULT 1
);

CREATE TABLE UserRoleMap (
    userRoleMapId   INT IDENTITY(1,1) PRIMARY KEY,
    userId          INT NOT NULL REFERENCES UserMaster(userId),
    roleId          INT NOT NULL REFERENCES RoleMaster(roleId),
    companyId       INT NOT NULL REFERENCES Company(companyId),
    isDefault       BIT NOT NULL DEFAULT 0,
    createdon       DATETIME NULL,
    createdby       INT      NULL,
    lastupdateon    DATETIME NULL,
    lastupdateby    INT      NULL,
    isActive        BIT      NOT NULL DEFAULT 1
);

CREATE TABLE ItemName (
    itemId          INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    itemGradeId     INT           NOT NULL REFERENCES ItemGrade(itemGradeId),
    itemName        NVARCHAR(100) NOT NULL,
    itemDia         NVARCHAR(50)  NULL,
    itemLength      NVARCHAR(50)  NULL,
    erpItemCode     NVARCHAR(50)  NULL,
    erpName         NVARCHAR(100) NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE CustomerMaster (
    customerId      INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    classificationId INT          NULL REFERENCES CustomerClassification(classificationId),
    customerCode    NVARCHAR(50)  NULL,
    customerName    NVARCHAR(200) NOT NULL,
    GSTN            NVARCHAR(50)  NULL,
    PAN             NVARCHAR(50)  NULL,
    siteId          INT           NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- ============================================================================
-- TIER 4: Tables with FKs to Tier 3
-- ============================================================================

CREATE TABLE ItemLength (
    itemLengthId    INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT          NOT NULL REFERENCES Company(companyId),
    itemId          INT          NOT NULL REFERENCES ItemName(itemId),
    itemLength      NVARCHAR(50) NOT NULL,
    createdon       DATETIME     NULL,
    createdby       INT          NULL,
    lastupdateon    DATETIME     NULL,
    lastupdateby    INT          NULL,
    isActive        BIT          NOT NULL DEFAULT 1
);

CREATE TABLE ItemSize (
    itemSizeId      INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT          NOT NULL REFERENCES Company(companyId),
    itemId          INT          NOT NULL REFERENCES ItemName(itemId),
    itemSize        NVARCHAR(50) NOT NULL,
    createdon       DATETIME     NULL,
    createdby       INT          NULL,
    lastupdateon    DATETIME     NULL,
    lastupdateby    INT          NULL,
    isActive        BIT          NOT NULL DEFAULT 1
);

CREATE TABLE CustomerContacts (
    customerContactId INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    customerId      INT           NOT NULL REFERENCES CustomerMaster(customerId),
    contactTypeId   INT           NULL REFERENCES ContactType(contactTypeId),
    contactPersonName NVARCHAR(100) NULL,
    designation     NVARCHAR(100) NULL,
    personalPhone   NVARCHAR(20)  NULL,
    personalEmail   NVARCHAR(100) NULL,
    officePhone     NVARCHAR(20)  NULL,
    officeEmail     NVARCHAR(100) NULL,
    address         NVARCHAR(500) NULL,
    state           NVARCHAR(100) NULL,
    dist            NVARCHAR(100) NULL,
    birthday        DATE          NULL,
    anniversary     DATE          NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE CustomerSite (
    siteId          INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    customerId      INT           NOT NULL REFERENCES CustomerMaster(customerId),
    siteAddressCode NVARCHAR(50)  NULL,
    addressLine     NVARCHAR(500) NULL,
    state           NVARCHAR(100) NULL,
    dist            NVARCHAR(100) NULL,
    PIN             NVARCHAR(20)  NULL,
    contactPerson1  NVARCHAR(100) NULL,
    contactPhone1   NVARCHAR(20)  NULL,
    contactEmail1   NVARCHAR(100) NULL,
    contactPerson2  NVARCHAR(100) NULL,
    contactPhone2   NVARCHAR(20)  NULL,
    contactEmail2   NVARCHAR(100) NULL,
    contactPerson3  NVARCHAR(100) NULL,
    contactPhone3   NVARCHAR(20)  NULL,
    contactEmail3   NVARCHAR(100) NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- ============================================================================
-- TIER 5: Enquiry tables
-- ============================================================================

CREATE TABLE CustomerEnquiry (
    enqid           INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    customerId      INT           NOT NULL REFERENCES CustomerMaster(customerId),
    customerContactId INT         NULL REFERENCES CustomerContacts(customerContactId),
    siteId          INT           NULL REFERENCES CustomerSite(siteId),
    enqNo           NVARCHAR(50)  NULL,
    enqDate         DATE          NULL,
    enqMode         NVARCHAR(50)  NULL,
    description     NVARCHAR(500) NULL,
    validityDays    INT           NULL,
    status          NVARCHAR(50)  NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE CustomerEnquiryDetails (
    enqdtlid        INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    enqid           INT           NOT NULL REFERENCES CustomerEnquiry(enqid),
    itemid          INT           NULL REFERENCES ItemName(itemId),
    itemGradeName   NVARCHAR(100) NULL,
    itemDia         NVARCHAR(50)  NULL,
    itemLength      NVARCHAR(50)  NULL,
    itemUnit        NVARCHAR(20)  NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- ============================================================================
-- TIER 6: Quotation tables (depends on Enquiry + Customer + Delivery)
-- ============================================================================

CREATE TABLE QuotSummary (
    quotId          INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    enqid           INT           NULL REFERENCES CustomerEnquiry(enqid),
    customerId      INT           NOT NULL REFERENCES CustomerMaster(customerId),
    customerContactId INT         NULL REFERENCES CustomerContacts(customerContactId),
    siteId          INT           NULL REFERENCES CustomerSite(siteId),
    quotNo          NVARCHAR(50)  NULL,
    quotDate        DATE          NULL,
    subject         NVARCHAR(500) NULL,
    deliveryTermId  INT           NULL REFERENCES DeliveryTerm(deliveryTermId),
    deliveryModeId  INT           NULL REFERENCES DeliveryMode(deliveryModeId),
    refQuotNo       NVARCHAR(50)  NULL,
    remarks         NVARCHAR(500) NULL,
    CustomerPONo    NVARCHAR(50)  NULL,
    CustomerPODate  DATE          NULL,
    revisionNo      INT           NULL,
    versionNo       INT           NOT NULL DEFAULT 1,
    parentQuotId    INT           NULL REFERENCES QuotSummary(quotId),
    approvedby      INT           NULL REFERENCES UserMaster(userId),
    approvedon      DATETIME      NULL,
    status          NVARCHAR(50)  NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

-- ============================================================================
-- TIER 7: Final dependent tables
-- ============================================================================

CREATE TABLE Asset (
    assetId         INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    enqid           INT           NULL REFERENCES CustomerEnquiry(enqid),
    quotId          INT           NULL REFERENCES QuotSummary(quotId),
    fileName        NVARCHAR(200) NOT NULL,
    fileUrl         NVARCHAR(500) NOT NULL,
    fileType        NVARCHAR(50)  NULL,
    fileSize        INT           NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);

CREATE TABLE CustomerEnquiryCosting (
    enqCostingId    INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT            NOT NULL REFERENCES Company(companyId),
    enqid           INT            NOT NULL REFERENCES CustomerEnquiry(enqid),
    enqdtlid        INT            NOT NULL REFERENCES CustomerEnquiryDetails(enqdtlid),
    versionNo       INT            NOT NULL DEFAULT 1,
    TPWGST          DECIMAL(18,2)  NULL,
    TPWoGST         DECIMAL(18,2)  NULL,
    costPoint1      DECIMAL(18,2)  NULL,
    costPoint2      DECIMAL(18,2)  NULL,
    costPoint3      DECIMAL(18,2)  NULL,
    costPoint4      DECIMAL(18,2)  NULL,
    costPoint5      DECIMAL(18,2)  NULL,
    costPoint6      DECIMAL(18,2)  NULL,
    costPoint7      DECIMAL(18,2)  NULL,
    costPoint8      DECIMAL(18,2)  NULL,
    costPoint9      DECIMAL(18,2)  NULL,
    costPoint10     DECIMAL(18,2)  NULL,
    costPoint11     DECIMAL(18,2)  NULL,
    costPoint12     DECIMAL(18,2)  NULL,
    costPoint13     DECIMAL(18,2)  NULL,
    costPoint14     DECIMAL(18,2)  NULL,
    costPoint15     DECIMAL(18,2)  NULL,
    costPoint16     DECIMAL(18,2)  NULL,
    costPoint17     DECIMAL(18,2)  NULL,
    costPoint18     DECIMAL(18,2)  NULL,
    costPoint19     DECIMAL(18,2)  NULL,
    costPoint20     DECIMAL(18,2)  NULL,
    basicRate       DECIMAL(18,2)  NULL,
    GST             DECIMAL(18,2)  NULL,
    EXFORPrice      DECIMAL(18,2)  NULL,
    createdon       DATETIME       NULL,
    createdby       INT            NULL,
    lastupdateon    DATETIME       NULL,
    lastupdateby    INT            NULL,
    isActive        BIT            NOT NULL DEFAULT 1
);

CREATE TABLE QuotDetails (
    quotDtlId       INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT            NOT NULL REFERENCES Company(companyId),
    quotId          INT            NOT NULL REFERENCES QuotSummary(quotId),
    itemGradeName   NVARCHAR(100)  NULL,
    itemDia         NVARCHAR(50)   NULL,
    itemLength      NVARCHAR(50)   NULL,
    itemUnit        NVARCHAR(20)   NULL,
    quantity        DECIMAL(18,2)  NULL,
    basicRate       DECIMAL(18,2)  NULL,
    IGST            DECIMAL(18,2)  NULL,
    CGST            DECIMAL(18,2)  NULL,
    SGST            DECIMAL(18,2)  NULL,
    totAmount       DECIMAL(18,2)  NULL,
    totRate         DECIMAL(18,2)  NULL,
    createdon       DATETIME       NULL,
    createdby       INT            NULL,
    lastupdateon    DATETIME       NULL,
    lastupdateby    INT            NULL,
    isActive        BIT            NOT NULL DEFAULT 1
);

CREATE TABLE QuotTermsNConditions (
    quotTncId       INT IDENTITY(1,1) PRIMARY KEY,
    companyId       INT           NOT NULL REFERENCES Company(companyId),
    quotId          INT           NOT NULL REFERENCES QuotSummary(quotId),
    tncName         NVARCHAR(200) NULL,
    tncDescription  NVARCHAR(500) NULL,
    createdon       DATETIME      NULL,
    createdby       INT           NULL,
    lastupdateon    DATETIME      NULL,
    lastupdateby    INT           NULL,
    isActive        BIT           NOT NULL DEFAULT 1
);
