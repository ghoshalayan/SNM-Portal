# SNM Portal - Database Schema

**Database:** SQL Server (via `pyodbc`)
**ORM:** SQLAlchemy 2.0
**Migrations:** Alembic

---

## Common Audit Columns (AuditMixin)

Every table includes these columns via `AuditMixin`:

| Column        | Type     | Notes                        |
|---------------|----------|------------------------------|
| createdon     | DateTime | Default `utcnow()`, nullable |
| createdby     | Integer  | nullable                     |
| lastupdateon  | DateTime | Auto-set on update, nullable |
| lastupdateby  | Integer  | nullable                     |
| isActive      | Boolean  | Default `True`, NOT NULL (soft delete flag) |

---

## Tables (28 total)

### 1. Company
**Table:** `Company`

| Column       | Type         | Constraints          |
|--------------|--------------|----------------------|
| companyId    | Integer (PK) | Auto-increment       |
| companyName  | String(100)  | NOT NULL             |
| companyCode  | String(50)   |                      |
| address      | String(500)  |                      |
| city         | String(100)  |                      |
| state        | String(100)  |                      |
| country      | String(100)  |                      |
| pinCode      | String(20)   |                      |
| phone        | String(20)   |                      |
| email        | String(100)  |                      |
| website      | String(200)  |                      |
| GSTN         | String(50)   |                      |
| PAN          | String(50)   |                      |
| logoUrl      | String(500)  |                      |
| MailFrom     | String(100)  | SMTP sender email    |
| MailPassword | String(200)  | SMTP password        |
| SMTP         | String(100)  | SMTP host            |
| PortNo       | String(10)   | SMTP port            |

---

### 2. UserMaster
**Table:** `UserMaster`

| Column       | Type         | Constraints                              |
|--------------|--------------|------------------------------------------|
| userId       | Integer (PK) | Auto-increment                           |
| companyId    | Integer (FK) | -> Company.companyId, NOT NULL           |
| userName     | String(100)  | NOT NULL                                 |
| userCode     | String(50)   |                                          |
| userEmail    | String(100)  |                                          |
| userPhone    | String(20)   |                                          |
| userLogin    | String(50)   | NOT NULL, UNIQUE                         |
| userPassword | String(255)  | NOT NULL (bcrypt hash)                   |
| reportTo     | Integer (FK) | -> UserMaster.userId (self-referential)  |

**Relationships:** `company`, `report_to_user` (self), `role_mappings` (-> UserRoleMap)

**Org Tree Convention:** `reportTo = userId` (self) = root node; `reportTo = NULL` = unassigned; `reportTo = other userId` = child node.

---

### 3. UserRoleMap
**Table:** `UserRoleMap`

| Column        | Type         | Constraints                    |
|---------------|--------------|--------------------------------|
| userRoleMapId | Integer (PK) | Auto-increment                |
| userId        | Integer (FK) | -> UserMaster.userId, NOT NULL |
| roleId        | Integer (FK) | -> RoleMaster.roleId, NOT NULL |
| companyId     | Integer (FK) | -> Company.companyId, NOT NULL |
| isDefault     | Boolean      | Default False, NOT NULL        |

**Purpose:** Multi-company user mapping. A user can belong to multiple companies with different roles. `isDefault` marks the primary company on login.

---

### 4. RoleMaster
**Table:** `RoleMaster`

| Column       | Type         | Constraints                    |
|--------------|--------------|--------------------------------|
| roleId       | Integer (PK) | Auto-increment                |
| companyId    | Integer (FK) | -> Company.companyId, NOT NULL |
| roleName     | String(100)  | NOT NULL                       |
| IsSuperAdmin | Boolean      | Default False, NOT NULL        |

---

### 5. MenuMaster
**Table:** `MenuMaster`

| Column       | Type         | Constraints                              |
|--------------|--------------|------------------------------------------|
| menuId       | Integer (PK) | Auto-increment                          |
| companyId    | Integer (FK) | -> Company.companyId, NOT NULL          |
| menuName     | String(100)  | NOT NULL                                 |
| menuUrl      | String(200)  | NULL for parent/grouping menus           |
| menuIcon     | String(100)  | Material icon name                       |
| parentMenuId | Integer (FK) | -> MenuMaster.menuId (self-referential)  |
| menuOrder    | Integer      | Default 0, NOT NULL                      |

**Relationships:** `parent` (self), `children` (backref)

---

### 6. RoleMenuMap
**Table:** `RoleMenuMap`

| Column        | Type         | Constraints                    |
|---------------|--------------|--------------------------------|
| roleMenuMapId | Integer (PK) | Auto-increment                |
| roleId        | Integer (FK) | -> RoleMaster.roleId, NOT NULL |
| menuId        | Integer (FK) | -> MenuMaster.menuId, NOT NULL |
| CanAdd        | Boolean      | Default False, NOT NULL        |
| CanRead       | Boolean      | Default False, NOT NULL        |
| CanEdit       | Boolean      | Default False, NOT NULL        |
| CanDelete     | Boolean      | Default False, NOT NULL        |

---

### 7. ItemGrade
**Table:** `ItemGrade`

| Column        | Type         | Constraints                    |
|---------------|--------------|--------------------------------|
| itemGradeId   | Integer (PK) | Auto-increment                |
| companyId     | Integer (FK) | -> Company.companyId, NOT NULL |
| itemGradeName | String(100)  | NOT NULL                       |

---

### 8. ItemName
**Table:** `ItemName`

| Column      | Type         | Constraints                        |
|-------------|--------------|------------------------------------|
| itemId      | Integer (PK) | Auto-increment                    |
| companyId   | Integer (FK) | -> Company.companyId, NOT NULL    |
| itemGradeId | Integer (FK) | -> ItemGrade.itemGradeId, NOT NULL |
| itemName    | String(100)  | NOT NULL                           |
| itemDia     | String(50)   |                                    |
| itemLength  | String(50)   |                                    |
| erpItemCode | String(50)   |                                    |
| erpName     | String(100)  |                                    |

---

### 9. ItemLength
**Table:** `ItemLength`

| Column       | Type         | Constraints                    |
|--------------|--------------|--------------------------------|
| itemLengthId | Integer (PK) | Auto-increment                |
| companyId    | Integer (FK) | -> Company.companyId, NOT NULL |
| itemId       | Integer (FK) | -> ItemName.itemId, NOT NULL   |
| itemLength   | String(50)   | NOT NULL                       |

---

### 10. ItemSize
**Table:** `ItemSize`

| Column     | Type         | Constraints                    |
|------------|--------------|--------------------------------|
| itemSizeId | Integer (PK) | Auto-increment                |
| companyId  | Integer (FK) | -> Company.companyId, NOT NULL |
| itemId     | Integer (FK) | -> ItemName.itemId, NOT NULL   |
| itemSize   | String(50)   | NOT NULL                       |

---

### 11. DeliveryTerm
**Table:** `DeliveryTerm`

| Column         | Type         | Constraints                    |
|----------------|--------------|--------------------------------|
| deliveryTermId | Integer (PK) | Auto-increment                |
| companyId      | Integer (FK) | -> Company.companyId, NOT NULL |
| deliveryTerm   | String(200)  | NOT NULL                       |

---

### 12. DeliveryMode
**Table:** `DeliveryMode`

| Column         | Type         | Constraints                    |
|----------------|--------------|--------------------------------|
| deliveryModeId | Integer (PK) | Auto-increment                |
| companyId      | Integer (FK) | -> Company.companyId, NOT NULL |
| deliveryMode   | String(200)  | NOT NULL                       |

---

### 13. CustomerClassification
**Table:** `CustomerClassification`

| Column             | Type         | Constraints                    |
|--------------------|--------------|--------------------------------|
| classificationId   | Integer (PK) | Auto-increment                |
| companyId          | Integer (FK) | -> Company.companyId, NOT NULL |
| classificationName | String(100)  | NOT NULL                       |

---

### 14. ContactType
**Table:** `ContactType`

| Column        | Type         | Constraints                    |
|---------------|--------------|--------------------------------|
| contactTypeId | Integer (PK) | Auto-increment                |
| companyId     | Integer (FK) | -> Company.companyId, NOT NULL |
| contactType   | String(100)  | NOT NULL                       |

---

### 15. CostPointMaster
**Table:** `CostPointMaster`

| Column        | Type         | Constraints                    |
|---------------|--------------|--------------------------------|
| costPointId   | Integer (PK) | Auto-increment                |
| companyId     | Integer (FK) | -> Company.companyId, NOT NULL |
| costPointName | String(100)  | NOT NULL                       |
| isPrimary     | Boolean      | Default False, NOT NULL        |
| isTax         | Boolean      | Default False, NOT NULL        |

---

### 16. CustomerMaster
**Table:** `CustomerMaster`

| Column           | Type         | Constraints                                  |
|------------------|--------------|----------------------------------------------|
| customerId       | Integer (PK) | Auto-increment                              |
| companyId        | Integer (FK) | -> Company.companyId, NOT NULL              |
| classificationId | Integer (FK) | -> CustomerClassification.classificationId  |
| customerCode     | String(50)   |                                              |
| customerName     | String(200)  | NOT NULL                                     |
| GSTN             | String(50)   |                                              |
| PAN              | String(50)   |                                              |
| siteId           | Integer      |                                              |

---

### 17. CustomerContacts
**Table:** `CustomerContacts`

| Column            | Type         | Constraints                            |
|-------------------|--------------|----------------------------------------|
| customerContactId | Integer (PK) | Auto-increment                        |
| companyId         | Integer (FK) | -> Company.companyId, NOT NULL        |
| customerId        | Integer (FK) | -> CustomerMaster.customerId, NOT NULL |
| contactTypeId     | Integer (FK) | -> ContactType.contactTypeId          |
| contactPersonName | String(100)  |                                        |
| designation       | String(100)  |                                        |
| personalPhone     | String(20)   |                                        |
| personalEmail     | String(100)  |                                        |
| officePhone       | String(20)   |                                        |
| officeEmail       | String(100)  |                                        |
| address           | String(500)  |                                        |
| state             | String(100)  |                                        |
| dist              | String(100)  |                                        |
| birthday          | Date         |                                        |
| anniversary       | Date         |                                        |

---

### 18. CustomerSite
**Table:** `CustomerSite`

| Column          | Type         | Constraints                            |
|-----------------|--------------|----------------------------------------|
| siteId          | Integer (PK) | Auto-increment                        |
| companyId       | Integer (FK) | -> Company.companyId, NOT NULL        |
| customerId      | Integer (FK) | -> CustomerMaster.customerId, NOT NULL |
| siteAddressCode | String(50)   |                                        |
| addressLine     | String(500)  |                                        |
| state           | String(100)  |                                        |
| dist            | String(100)  |                                        |
| PIN             | String(20)   |                                        |
| contactPerson1  | String(100)  |                                        |
| contactPhone1   | String(20)   |                                        |
| contactEmail1   | String(100)  |                                        |
| contactPerson2  | String(100)  |                                        |
| contactPhone2   | String(20)   |                                        |
| contactEmail2   | String(100)  |                                        |
| contactPerson3  | String(100)  |                                        |
| contactPhone3   | String(20)   |                                        |
| contactEmail3   | String(100)  |                                        |

---

### 19. CustomerEnquiry
**Table:** `CustomerEnquiry`

| Column            | Type         | Constraints                                    |
|-------------------|--------------|------------------------------------------------|
| enqid             | Integer (PK) | Auto-increment                                |
| companyId         | Integer (FK) | -> Company.companyId, NOT NULL                |
| customerId        | Integer (FK) | -> CustomerMaster.customerId, NOT NULL        |
| customerContactId | Integer (FK) | -> CustomerContacts.customerContactId         |
| siteId            | Integer (FK) | -> CustomerSite.siteId                        |
| enqNo             | String(50)   |                                                |
| enqDate           | Date         |                                                |
| enqMode           | String(50)   |                                                |
| description       | String(500)  |                                                |
| validityDays      | Integer      |                                                |
| status            | String(50)   | Default "Open"                                 |

---

### 20. CustomerEnquiryDetails
**Table:** `CustomerEnquiryDetails`

| Column        | Type         | Constraints                          |
|---------------|--------------|--------------------------------------|
| enqdtlid      | Integer (PK) | Auto-increment                      |
| companyId     | Integer (FK) | -> Company.companyId, NOT NULL      |
| enqid         | Integer (FK) | -> CustomerEnquiry.enqid, NOT NULL  |
| itemid        | Integer (FK) | -> ItemName.itemId                  |
| itemGradeName | String(100)  |                                      |
| itemDia       | String(50)   |                                      |
| itemLength    | String(50)   |                                      |
| itemUnit      | String(20)   |                                      |

---

### 21. CustomerEnquiryCosting
**Table:** `CustomerEnquiryCosting`

| Column       | Type           | Constraints                                     |
|--------------|----------------|-------------------------------------------------|
| enqCostingId | Integer (PK)   | Auto-increment                                 |
| companyId    | Integer (FK)   | -> Company.companyId, NOT NULL                 |
| enqid        | Integer (FK)   | -> CustomerEnquiry.enqid, NOT NULL             |
| enqdtlid     | Integer (FK)   | -> CustomerEnquiryDetails.enqdtlid, NOT NULL   |
| versionNo    | Integer        | Default 1, NOT NULL                             |
| TPWGST       | Numeric(18,2)  |                                                 |
| TPWoGST      | Numeric(18,2)  |                                                 |
| costPoint1-20| Numeric(18,2)  | 20 individual cost point columns                |
| basicRate    | Numeric(18,2)  |                                                 |
| GST          | Numeric(18,2)  |                                                 |
| EXFORPrice   | Numeric(18,2)  |                                                 |

**Versioning:** New version = new row with `versionNo + 1`, same `enqid` + `enqdtlid`. Latest = `MAX(versionNo)`.

---

### 22. QuotSummary
**Table:** `QuotSummary`

| Column            | Type         | Constraints                                    |
|-------------------|--------------|------------------------------------------------|
| quotId            | Integer (PK) | Auto-increment                                |
| companyId         | Integer (FK) | -> Company.companyId, NOT NULL                |
| enqid             | Integer (FK) | -> CustomerEnquiry.enqid                      |
| customerId        | Integer (FK) | -> CustomerMaster.customerId, NOT NULL        |
| customerContactId | Integer (FK) | -> CustomerContacts.customerContactId         |
| siteId            | Integer (FK) | -> CustomerSite.siteId                        |
| quotNo            | String(50)   |                                                |
| quotDate          | Date         |                                                |
| subject           | String(500)  |                                                |
| deliveryTermId    | Integer (FK) | -> DeliveryTerm.deliveryTermId                |
| deliveryModeId    | Integer (FK) | -> DeliveryMode.deliveryModeId                |
| refQuotNo         | String(50)   |                                                |
| remarks           | String(500)  |                                                |
| CustomerPONo      | String(50)   |                                                |
| CustomerPODate    | Date         |                                                |
| revisionNo        | Integer      | Default 0                                      |
| versionNo         | Integer      | Default 1, NOT NULL                            |
| parentQuotId      | Integer (FK) | -> QuotSummary.quotId (self-referential)       |
| approvedby        | Integer (FK) | -> UserMaster.userId                           |
| approvedon        | DateTime     |                                                |
| status            | String(50)   | Default "Draft"                                |

**Versioning:** "Revise Quotation" creates a new row with `versionNo + 1`, `parentQuotId` = original. Format: `QUOT-001-R1`.

---

### 23. QuotDetails
**Table:** `QuotDetails`

| Column        | Type           | Constraints                        |
|---------------|----------------|------------------------------------|
| quotDtlId     | Integer (PK)   | Auto-increment                    |
| companyId     | Integer (FK)   | -> Company.companyId, NOT NULL    |
| quotId        | Integer (FK)   | -> QuotSummary.quotId, NOT NULL   |
| itemGradeName | String(100)    |                                    |
| itemDia       | String(50)     |                                    |
| itemLength    | String(50)     |                                    |
| itemUnit      | String(20)     |                                    |
| quantity      | Numeric(18,2)  |                                    |
| basicRate     | Numeric(18,2)  |                                    |
| IGST          | Numeric(18,2)  |                                    |
| CGST          | Numeric(18,2)  |                                    |
| SGST          | Numeric(18,2)  |                                    |
| totAmount     | Numeric(18,2)  |                                    |
| totRate       | Numeric(18,2)  |                                    |

---

### 24. QuotTermsNConditions
**Table:** `QuotTermsNConditions`

| Column         | Type         | Constraints                        |
|----------------|--------------|------------------------------------|
| quotTncId      | Integer (PK) | Auto-increment                    |
| companyId      | Integer (FK) | -> Company.companyId, NOT NULL    |
| quotId         | Integer (FK) | -> QuotSummary.quotId, NOT NULL   |
| tncName        | String(200)  |                                    |
| tncDescription | String(500)  |                                    |

---

### 25. TermsNConditionMaster
**Table:** `TermsNConditionMaster`

| Column         | Type         | Constraints                    |
|----------------|--------------|--------------------------------|
| tncId          | Integer (PK) | Auto-increment                |
| companyId      | Integer (FK) | -> Company.companyId, NOT NULL |
| tncName        | String(200)  | NOT NULL                       |
| tncDescription | String(500)  |                                |

---

### 26. RawMaterialCost
**Table:** `RawMaterialCost`

| Column            | Type           | Constraints                    |
|-------------------|----------------|--------------------------------|
| rawMaterialCostId | Integer (PK)   | Auto-increment                |
| companyId         | Integer (FK)   | -> Company.companyId, NOT NULL |
| dia               | String(50)     | NOT NULL                       |
| tpcost            | Numeric(18,2)  | NOT NULL                       |
| effectedFrom      | DateTime       |                                |

---

### 27. Asset
**Table:** `Asset`

| Column    | Type         | Constraints                        |
|-----------|--------------|------------------------------------|
| assetId   | Integer (PK) | Auto-increment                    |
| companyId | Integer (FK) | -> Company.companyId, NOT NULL    |
| enqid     | Integer (FK) | -> CustomerEnquiry.enqid          |
| quotId    | Integer (FK) | -> QuotSummary.quotId             |
| fileName  | String(200)  | NOT NULL                           |
| fileUrl   | String(500)  | NOT NULL                           |
| fileType  | String(50)   |                                    |
| fileSize  | Integer      |                                    |

---

### 28. Country
**Table:** `Country`

| Column      | Type         | Constraints    |
|-------------|--------------|----------------|
| countryid   | Integer (PK) | Auto-increment |
| countryname | String(50)   | NOT NULL       |

---

### 29. StateMaster
**Table:** `StateMaster`

| Column    | Type         | Constraints    |
|-----------|--------------|----------------|
| stateid   | Integer (PK) | Auto-increment |
| StateName | String(50)   | NOT NULL       |
| Country   | String(50)   |                |

---

### 30. DistrictMaster
**Table:** `DistrictMaster`

| Column      | Type         | Constraints    |
|-------------|--------------|----------------|
| districtid  | Integer (PK) | Auto-increment |
| districName | String(50)   | NOT NULL       |
| StateName   | String(50)   |                |
| Country     | String(50)   |                |

---

### 31. DiaMaster
**Table:** `DiaMaster`

| Column         | Type         | Constraints                    |
|----------------|--------------|--------------------------------|
| diaid          | Integer (PK) | Auto-increment                |
| itemid         | Integer (FK) | -> ItemName.itemId, NOT NULL   |
| diadescription | String(50)   | NOT NULL                       |
| companyId      | Integer (FK) | -> Company.companyId, NOT NULL |

---

## Entity Relationship Summary

```
Company (1) ──< UserMaster (many)
Company (1) ──< RoleMaster (many)
Company (1) ──< MenuMaster (many)
Company (1) ──< All master tables (many)

UserMaster (1) ──< UserRoleMap (many) >── RoleMaster (1)
UserMaster.reportTo ──> UserMaster.userId (self-referential)

RoleMaster (1) ──< RoleMenuMap (many) >── MenuMaster (1)
MenuMaster.parentMenuId ──> MenuMaster.menuId (self-referential, unlimited nesting)

CustomerMaster (1) ──< CustomerContacts (many)
CustomerMaster (1) ──< CustomerSite (many)

CustomerEnquiry (1) ──< CustomerEnquiryDetails (many)
CustomerEnquiryDetails (1) ──< CustomerEnquiryCosting (many, versioned)

QuotSummary (1) ──< QuotDetails (many)
QuotSummary (1) ──< QuotTermsNConditions (many)
QuotSummary.parentQuotId ──> QuotSummary.quotId (self-referential, versioning)

ItemGrade (1) ──< ItemName (many)
ItemName (1) ──< ItemLength (many)
ItemName (1) ──< ItemSize (many)
ItemName (1) ──< DiaMaster (many)
```

## Multi-Tenancy

Every query is filtered by `companyId` extracted from the JWT token. All tables (except Country, StateMaster, DistrictMaster) are company-scoped.
