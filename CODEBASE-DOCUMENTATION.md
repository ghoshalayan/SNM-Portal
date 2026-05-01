# SNM Portal - Codebase Documentation

**Stack:** FastAPI + Angular 19 + SQL Server + SQLAlchemy + Alembic + Angular Material + JWT Auth + Azure Blob Storage

---

## Table of Contents

1. [Database Schema](#1-database-schema)
2. [Migrations](#2-migrations)
3. [Backend Architecture](#3-backend-architecture)
4. [Frontend Architecture](#4-frontend-architecture)
5. [High-Level Flows](#5-high-level-flows)
6. [Known Bugs & Issues](#6-known-bugs--issues)

---

## 1. Database Schema

### Audit Mixin (All Tables)

Every table inherits these columns via `AuditMixin`:

| Column | Type | Notes |
|--------|------|-------|
| createdon | DateTime | Default: utcnow |
| createdby | Integer | Nullable |
| lastupdateon | DateTime | Auto-updated on change |
| lastupdateby | Integer | Nullable |
| isActive | Boolean | Default: True (soft delete flag) |

---

### 1.1 Company

**Table:** `Company`

| Column | Type | Constraint |
|--------|------|------------|
| companyId | Integer | PK, auto-increment |
| companyName | String(100) | NOT NULL |
| companyCode | String(50) | Nullable |
| address | String(500) | Nullable |
| city | String(100) | Nullable |
| state | String(100) | Nullable |
| country | String(100) | Nullable |
| pinCode | String(20) | Nullable |
| phone | String(20) | Nullable |
| email | String(100) | Nullable |
| website | String(200) | Nullable |
| GSTN | String(50) | Nullable |
| PAN | String(50) | Nullable |
| logoUrl | String(500) | Nullable |
| MailFrom | String(100) | Nullable |
| MailPassword | String(200) | Nullable |
| SMTP | String(100) | Nullable |
| PortNo | String(10) | Nullable |

---

### 1.2 UserMaster

**Table:** `UserMaster`

| Column | Type | Constraint |
|--------|------|------------|
| userId | Integer | PK, auto-increment |
| companyId | Integer | FK -> Company, NOT NULL |
| userName | String(100) | NOT NULL |
| userCode | String(50) | Nullable |
| userEmail | String(100) | Nullable |
| userPhone | String(20) | Nullable |
| userLogin | String(50) | NOT NULL, UNIQUE |
| userPassword | String(255) | NOT NULL (bcrypt hash) |
| reportTo | Integer | FK -> UserMaster (self), Nullable |

**Relationships:** company, report_to_user (self-ref), role_mappings

---

### 1.3 UserRoleMap

**Table:** `UserRoleMap`

| Column | Type | Constraint |
|--------|------|------------|
| userRoleMapId | Integer | PK, auto-increment |
| userId | Integer | FK -> UserMaster, NOT NULL |
| roleId | Integer | FK -> RoleMaster, NOT NULL |
| companyId | Integer | FK -> Company, NOT NULL |
| isDefault | Boolean | Default: False, NOT NULL |

**Purpose:** Maps users to multiple companies, each with a different role.

---

### 1.4 RoleMaster

**Table:** `RoleMaster`

| Column | Type | Constraint |
|--------|------|------------|
| roleId | Integer | PK, auto-increment |
| companyId | Integer | FK -> Company, NOT NULL |
| roleName | String(100) | NOT NULL |
| IsSuperAdmin | Boolean | Default: False, NOT NULL |

---

### 1.5 MenuMaster

**Table:** `MenuMaster` (self-referencing tree)

| Column | Type | Constraint |
|--------|------|------------|
| menuId | Integer | PK, auto-increment |
| companyId | Integer | FK -> Company, NOT NULL |
| menuName | String(100) | NOT NULL |
| menuUrl | String(200) | Nullable |
| menuIcon | String(100) | Nullable |
| parentMenuId | Integer | FK -> MenuMaster (self), Nullable |
| menuOrder | Integer | Default: 0, NOT NULL |

---

### 1.6 RoleMenuMap

**Table:** `RoleMenuMap`

| Column | Type | Constraint |
|--------|------|------------|
| roleMenuMapId | Integer | PK, auto-increment |
| roleId | Integer | FK -> RoleMaster, NOT NULL |
| menuId | Integer | FK -> MenuMaster, NOT NULL |
| CanAdd | Boolean | Default: False |
| CanRead | Boolean | Default: False |
| CanEdit | Boolean | Default: False |
| CanDelete | Boolean | Default: False |

---

### 1.7 Item Tables

**Table:** `ItemGrade`

| Column | Type | Constraint |
|--------|------|------------|
| itemGradeId | Integer | PK |
| companyId | Integer | FK -> Company |
| itemGradeName | String(100) | NOT NULL |

**Table:** `ItemName`

| Column | Type | Constraint |
|--------|------|------------|
| itemId | Integer | PK |
| companyId | Integer | FK -> Company |
| itemGradeId | Integer | FK -> ItemGrade |
| itemName | String(100) | NOT NULL |
| itemDia | String(50) | Nullable |
| itemLength | String(50) | Nullable |
| erpItemCode | String(50) | Nullable |
| erpName | String(100) | Nullable |

**Table:** `ItemLength`

| Column | Type | Constraint |
|--------|------|------------|
| itemLengthId | Integer | PK |
| companyId | Integer | FK -> Company |
| itemId | Integer | FK -> ItemName |
| itemLength | String(50) | NOT NULL |

**Table:** `ItemSize`

| Column | Type | Constraint |
|--------|------|------------|
| itemSizeId | Integer | PK |
| companyId | Integer | FK -> Company |
| itemId | Integer | FK -> ItemName |
| itemSize | String(50) | NOT NULL |

---

### 1.8 Delivery Tables

**Table:** `DeliveryTerm`

| Column | Type | Constraint |
|--------|------|------------|
| deliveryTermId | Integer | PK |
| companyId | Integer | FK -> Company |
| deliveryTerm | String(200) | NOT NULL |

**Table:** `DeliveryMode`

| Column | Type | Constraint |
|--------|------|------------|
| deliveryModeId | Integer | PK |
| companyId | Integer | FK -> Company |
| deliveryMode | String(200) | NOT NULL |

---

### 1.9 Other Masters

**Table:** `CustomerClassification`

| Column | Type |
|--------|------|
| classificationId | Integer PK |
| companyId | FK -> Company |
| classificationName | String(100) NOT NULL |

**Table:** `ContactType`

| Column | Type |
|--------|------|
| contactTypeId | Integer PK |
| companyId | FK -> Company |
| contactType | String(100) NOT NULL |

**Table:** `CostPointMaster`

| Column | Type |
|--------|------|
| costPointId | Integer PK |
| companyId | FK -> Company |
| costPointName | String(100) NOT NULL |
| isPrimary | Boolean, Default: False |
| isTax | Boolean, Default: False |

**Table:** `TermsNConditionMaster`

| Column | Type |
|--------|------|
| tncId | Integer PK |
| companyId | FK -> Company |
| tncName | String(200) NOT NULL |
| tncDescription | String(500) Nullable |

**Table:** `RawMaterialCost`

| Column | Type |
|--------|------|
| rawMaterialCostId | Integer PK |
| companyId | FK -> Company |
| dia | String(50) NOT NULL |
| tpcost | Numeric(18,2) NOT NULL |
| effectedFrom | DateTime Nullable |

---

### 1.10 Customer Tables

**Table:** `CustomerMaster`

| Column | Type | Constraint |
|--------|------|------------|
| customerId | Integer | PK |
| companyId | Integer | FK -> Company |
| classificationId | Integer | FK -> CustomerClassification, Nullable |
| customerCode | String(50) | Nullable |
| customerName | String(200) | NOT NULL |
| GSTN | String(50) | Nullable |
| PAN | String(50) | Nullable |
| siteId | Integer | Nullable |

**Relationships:** classification, contacts (back_populates), sites (back_populates)

**Table:** `CustomerContacts`

| Column | Type | Constraint |
|--------|------|------------|
| customerContactId | Integer | PK |
| companyId | Integer | FK -> Company |
| customerId | Integer | FK -> CustomerMaster |
| contactTypeId | Integer | FK -> ContactType, Nullable |
| contactPersonName | String(100) | Nullable |
| designation | String(100) | Nullable |
| personalPhone | String(20) | Nullable |
| personalEmail | String(100) | Nullable |
| officePhone | String(20) | Nullable |
| officeEmail | String(100) | Nullable |
| address | String(500) | Nullable |
| state | String(100) | Nullable |
| dist | String(100) | Nullable |
| birthday | Date | Nullable |
| anniversary | Date | Nullable |

**Table:** `CustomerSite`

| Column | Type | Constraint |
|--------|------|------------|
| siteId | Integer | PK |
| companyId | Integer | FK -> Company |
| customerId | Integer | FK -> CustomerMaster |
| siteAddressCode | String(50) | Nullable |
| addressLine | String(500) | Nullable |
| state | String(100) | Nullable |
| dist | String(100) | Nullable |
| PIN | String(20) | Nullable |
| contactPerson1-3 | String(100) | Nullable (x3) |
| contactPhone1-3 | String(20) | Nullable (x3) |
| contactEmail1-3 | String(100) | Nullable (x3) |

---

### 1.11 Enquiry Tables

**Table:** `CustomerEnquiry`

| Column | Type | Constraint |
|--------|------|------------|
| enqid | Integer | PK |
| companyId | Integer | FK -> Company |
| customerId | Integer | FK -> CustomerMaster |
| customerContactId | Integer | FK -> CustomerContacts, Nullable |
| siteId | Integer | FK -> CustomerSite, Nullable |
| enqNo | String(50) | Nullable |
| enqDate | Date | Nullable |
| enqMode | String(50) | Nullable |
| description | String(500) | Nullable |
| validityDays | Integer | Nullable |
| status | String(50) | Default: "Open" |

**Table:** `CustomerEnquiryDetails`

| Column | Type | Constraint |
|--------|------|------------|
| enqdtlid | Integer | PK |
| companyId | Integer | FK -> Company |
| enqid | Integer | FK -> CustomerEnquiry |
| itemid | Integer | FK -> ItemName, Nullable |
| itemGradeName | String(100) | Nullable |
| itemDia | String(50) | Nullable |
| itemLength | String(50) | Nullable |
| itemUnit | String(20) | Nullable |

**Table:** `CustomerEnquiryCosting` (versioned)

| Column | Type | Constraint |
|--------|------|------------|
| enqCostingId | Integer | PK |
| companyId | Integer | FK -> Company |
| enqid | Integer | FK -> CustomerEnquiry |
| enqdtlid | Integer | FK -> CustomerEnquiryDetails |
| versionNo | Integer | Default: 1, NOT NULL |
| TPWGST | Numeric(18,2) | TP With GST |
| TPWoGST | Numeric(18,2) | TP Without GST |
| costPoint1-20 | Numeric(18,2) | 20 flexible cost points |
| basicRate | Numeric(18,2) | Nullable |
| GST | Numeric(18,2) | Nullable |
| EXFORPrice | Numeric(18,2) | Ex-Factory Price |

---

### 1.12 Quotation Tables

**Table:** `QuotSummary` (versioned)

| Column | Type | Constraint |
|--------|------|------------|
| quotId | Integer | PK |
| companyId | Integer | FK -> Company |
| enqid | Integer | FK -> CustomerEnquiry, Nullable |
| customerId | Integer | FK -> CustomerMaster |
| customerContactId | Integer | FK -> CustomerContacts, Nullable |
| siteId | Integer | FK -> CustomerSite, Nullable |
| quotNo | String(50) | Nullable |
| quotDate | Date | Nullable |
| subject | String(500) | Nullable |
| deliveryTermId | Integer | FK -> DeliveryTerm, Nullable |
| deliveryModeId | Integer | FK -> DeliveryMode, Nullable |
| refQuotNo | String(50) | Nullable |
| remarks | String(500) | Nullable |
| CustomerPONo | String(50) | Nullable |
| CustomerPODate | Date | Nullable |
| revisionNo | Integer | Default: 0 |
| versionNo | Integer | Default: 1, NOT NULL |
| parentQuotId | Integer | FK -> QuotSummary (self), Nullable |
| approvedby | Integer | FK -> UserMaster, Nullable |
| approvedon | DateTime | Nullable |
| status | String(50) | Default: "Draft" |

**Table:** `QuotDetails`

| Column | Type | Constraint |
|--------|------|------------|
| quotDtlId | Integer | PK |
| companyId | Integer | FK -> Company |
| quotId | Integer | FK -> QuotSummary |
| itemGradeName | String(100) | Nullable |
| itemDia | String(50) | Nullable |
| itemLength | String(50) | Nullable |
| itemUnit | String(20) | Nullable |
| quantity | Numeric(18,2) | Nullable |
| basicRate | Numeric(18,2) | Nullable |
| IGST | Numeric(18,2) | Nullable |
| CGST | Numeric(18,2) | Nullable |
| SGST | Numeric(18,2) | Nullable |
| totAmount | Numeric(18,2) | Nullable |
| totRate | Numeric(18,2) | Nullable |

**Table:** `QuotTermsNConditions`

| Column | Type | Constraint |
|--------|------|------------|
| quotTncId | Integer | PK |
| companyId | Integer | FK -> Company |
| quotId | Integer | FK -> QuotSummary |
| tncName | String(200) | Nullable |
| tncDescription | String(500) | Nullable |

---

### 1.13 Asset

**Table:** `Asset`

| Column | Type | Constraint |
|--------|------|------------|
| assetId | Integer | PK |
| companyId | Integer | FK -> Company |
| enqid | Integer | FK -> CustomerEnquiry, Nullable |
| quotId | Integer | FK -> QuotSummary, Nullable |
| fileName | String(200) | NOT NULL |
| fileUrl | String(500) | NOT NULL |
| fileType | String(50) | Nullable |
| fileSize | Integer | Nullable |

---

### Entity Relationship Summary

```
Company (root)
  |-- UserMaster (companyId)
  |     |-- UserRoleMap (userId, roleId, companyId)
  |-- RoleMaster (companyId)
  |     |-- RoleMenuMap (roleId, menuId)
  |-- MenuMaster (companyId, parentMenuId -> self)
  |-- ItemGrade (companyId)
  |     |-- ItemName (itemGradeId)
  |           |-- ItemLength (itemId)
  |           |-- ItemSize (itemId)
  |-- DeliveryTerm (companyId)
  |-- DeliveryMode (companyId)
  |-- CustomerClassification (companyId)
  |-- ContactType (companyId)
  |-- CostPointMaster (companyId)
  |-- TermsNConditionMaster (companyId)
  |-- RawMaterialCost (companyId)
  |-- CustomerMaster (companyId, classificationId)
  |     |-- CustomerContacts (customerId, contactTypeId)
  |     |-- CustomerSite (customerId)
  |-- CustomerEnquiry (customerId, contactId, siteId)
  |     |-- CustomerEnquiryDetails (enqid, itemid)
  |     |-- CustomerEnquiryCosting (enqid, enqdtlid) [versioned]
  |-- QuotSummary (enqid, customerId, parentQuotId -> self) [versioned]
  |     |-- QuotDetails (quotId)
  |     |-- QuotTermsNConditions (quotId)
  |-- Asset (enqid, quotId)
```

---

## 2. Migrations

### Migration Chain

```
9eaf9699f05f  Initial schema - all 25 tables
      |
e88c297e3e9d  Seed superadmin, test user, company, menus, permissions
      |
f3a1b2c4d5e6  Fix menu URLs singular to plural
```

### Migration 1: `9eaf9699f05f` - Initial Schema
- Creates all 25 tables with columns, foreign keys, and audit fields
- All IDs are auto-increment identity columns
- All tables have AuditMixin fields

### Migration 2: `e88c297e3e9d` - Seed Data
- **Company:** "SNM Default Company" (code: SNM, Mumbai, Maharashtra, India)
- **Roles:** "Super Admin" (isSuperAdmin=true), "Standard User"
- **Users:**
  - admin / Admin@123 (Super Administrator, SADMIN)
  - testuser / Test@123 (Test User, TUSER)
- **UserRoleMap:** admin -> Super Admin, testuser -> Standard User
- **Menus:** 24 hierarchical menu items (Dashboard, Administration, Masters, Customers, Enquiries, Quotations, Assets)
- **Permissions:** Super Admin = full CRUD on all; Standard User = read on Dashboard/Customers, full CRUD on Enquiries/Quotations/Assets

### Migration 3: `f3a1b2c4d5e6` - URL Fix
- Corrects menu URLs from singular to plural to match Angular routes
- e.g., `/masters/item-grade` -> `/masters/item-grades`

---

## 3. Backend Architecture

### Project Structure

```
backend/
  app/
    main.py              # FastAPI app, CORS, /health endpoint
    core/
      config.py          # Settings (DB, JWT, Azure, SMTP, CORS)
      database.py        # SQLAlchemy engine, SessionLocal, Base
      security.py        # JWT create/decode, bcrypt hash/verify
      dependencies.py    # get_db, get_current_user, require_permission, require_super_admin
      email.py           # Re-exports email_service
    models/              # SQLAlchemy ORM models (18 classes, 14 files)
      base.py            # AuditMixin
      company.py, user.py, role.py, menu.py, role_menu_map.py,
      item.py, delivery.py, customer_classification.py, contact_type.py,
      cost_point.py, terms_condition.py, raw_material_cost.py,
      customer.py, enquiry.py, quotation.py, asset.py
    schemas/             # Pydantic request/response models
      auth.py, company.py, user.py, role.py, menu.py,
      customer.py, enquiry.py, quotation.py
    services/            # Business logic layer
      auth_service.py, menu_service.py, costing_service.py,
      quotation_service.py, company_setup_service.py,
      azure_blob_service.py, email_service.py
    api/v1/              # Route handlers
      router.py          # Aggregates all routers under /api/v1
      auth.py, company.py, users.py, roles.py, menus.py,
      masters.py, customers.py, enquiries.py, quotations.py,
      assets.py, email.py
  alembic/               # Database migrations
```

### API Endpoints Summary

| Base Path | Methods | Auth | Description |
|-----------|---------|------|-------------|
| /api/v1/auth | POST /login, /select-company, /switch-company, /refresh; GET /my-companies | Public/Bearer | Authentication & company selection |
| /api/v1/users | GET, POST, PUT, DELETE; /{id}/role-mappings | Bearer | User CRUD + role mapping |
| /api/v1/roles | GET, POST, PUT, DELETE | Bearer + Company | Role CRUD |
| /api/v1/companies | GET, POST, PUT, DELETE | Bearer + SuperAdmin | Company CRUD (super admin only) |
| /api/v1/menus | GET, GET /tree, GET /user-tree, POST, PUT, DELETE; /role-menu-map/{roleId} | Bearer | Menu CRUD + permission mapping |
| /api/v1/masters/* | GET, POST, PUT, DELETE for each master type | Bearer + Company | 11 master data types |
| /api/v1/customers | CRUD + /{id}/contacts + /{id}/sites | Bearer + Company | Customer with contacts & sites |
| /api/v1/enquiries | CRUD + /{id}/details + /{id}/costing + /costing/new-version | Bearer + Company | Enquiry lifecycle + versioned costing |
| /api/v1/quotations | CRUD + /{id}/revise + /{id}/approve + /{id}/details + /{id}/terms | Bearer + Company | Quotation lifecycle + versioning |
| /api/v1/assets | GET, POST /upload, GET /{id}/download, DELETE | Bearer + Company | Azure Blob file management |
| /api/v1/email | POST /send-quotation, POST /test-smtp | Bearer | Email via company SMTP config |

### Authentication Flow

1. `POST /auth/login` -> validates credentials -> returns `tempToken` + list of user's companies
2. `POST /auth/select-company` (with tempToken) -> returns `accessToken` + `refreshToken`
3. JWT payload: `{ user_id, company_id, role_id, is_super_admin, type, exp }`
4. Access token: 30min expiry; Refresh token: 7 days
5. `POST /auth/switch-company` -> re-issues tokens for new company

### Key Services

| Service | Purpose |
|---------|---------|
| `auth_service` | Authenticate users, validate company access, create tokens |
| `menu_service` | Build menu trees, filter by role permissions |
| `costing_service` | Auto-fill TP costs, create costing versions |
| `quotation_service` | Create quotation revisions with detail/T&C copying |
| `company_setup_service` | Seed default menus, roles, and permissions for new companies |
| `azure_blob_service` | Upload/download/delete files, generate SAS URLs |
| `email_service` | Send emails via company SMTP, template filling |

---

## 4. Frontend Architecture

### Project Structure

```
frontend/src/app/
  app.config.ts             # Providers (router, HTTP, animations, interceptor)
  app.routes.ts             # All routes with lazy loading
  app.ts                    # Root component
  core/
    auth/
      auth.service.ts       # Login, token management, company switching
      auth.guard.ts         # CanActivate guard -> /login redirect
      auth.interceptor.ts   # Adds Bearer token, handles 401
      token.service.ts      # localStorage for tokens + user data
    services/
      api.service.ts        # Generic HTTP wrapper (get/post/put/delete)
      menu.service.ts       # Menu tree loading, permission checks
      notification.service.ts  # MatSnackBar wrapper
      company-context.service.ts  # Company switch orchestration
  layout/
    main-layout/            # App shell: sidenav + toolbar + router-outlet
  shared/
    components/
      dynamic-menu/         # Recursive sidebar menu from MenuService
      company-switcher/     # Company dropdown in toolbar
      confirm-dialog/       # Reusable confirm dialog
      skeleton-loader/      # Loading skeletons (table, menu, toolbar, text)
      profile-menu/         # Profile dialog with change password
    directives/
      has-permission.directive.ts  # *appHasPermission="'Menu:canAction'"
  features/
    auth/login/             # Login + company picker
    dashboard/              # Welcome page
    company/                # Company list + dialog (super admin)
    users/                  # User list + dialog
    roles/                  # Role list + dialog + role-menu-mapping
    masters/                # 11 master modules (list + dialog each)
    customers/              # List + form (tabs: info, contacts, sites)
    enquiries/              # List + form (tabs: info, details, costing)
    quotations/             # List + form (tabs: info, details, T&C, versions) + print
    assets/                 # Asset upload component
```

### Routing Map

```
/login                          -> LoginComponent
/ (MainLayoutComponent)
  /dashboard                    -> DashboardComponent
  /companies                    -> CompanyListComponent
  /users                        -> UserListComponent
  /roles                        -> RoleListComponent
  /roles/:roleId/menu-mapping   -> RoleMenuMappingComponent
  /masters/item-grades          -> ItemGradeListComponent
  /masters/item-names           -> ItemNameListComponent
  /masters/item-lengths         -> ItemLengthListComponent
  /masters/item-sizes           -> ItemSizeListComponent
  /masters/delivery-terms       -> DeliveryTermListComponent
  /masters/delivery-modes       -> DeliveryModeListComponent
  /masters/contact-types        -> ContactTypeListComponent
  /masters/customer-classifications -> CustomerClassificationListComponent
  /masters/cost-points          -> CostPointListComponent
  /masters/terms-conditions     -> TermsConditionListComponent
  /masters/raw-material-costs   -> RawMaterialCostListComponent
  /customers                    -> CustomerListComponent
  /customers/new                -> CustomerFormComponent
  /customers/:id/edit           -> CustomerFormComponent
  /enquiries                    -> EnquiryListComponent
  /enquiries/new                -> EnquiryFormComponent
  /enquiries/:id/edit           -> EnquiryFormComponent
  /quotations                   -> QuotationListComponent
  /quotations/new               -> QuotationFormComponent
  /quotations/:id/edit          -> QuotationFormComponent
  /quotations/:id/print         -> QuotationPrintComponent
  (default)                     -> redirect to /dashboard
/** (wildcard)                  -> redirect to /login
```

### UI Patterns

**Pattern 1: List + Dialog (Masters, Users, Roles, Companies)**
- MatTable with MatPaginator, MatSort, search filter
- 500ms minimum skeleton loader delay
- Add/Edit via MatDialog
- Delete with ConfirmDialog
- Soft-delete via API

**Pattern 2: Multi-Tab Form (Customers, Enquiries, Quotations)**
- Tab 1: Main entity form
- Tab 2+: Child entities (disabled until parent saved)
- Separate components per tab

**Pattern 3: Glassmorphism Design System**
- All cards: rgba(255,255,255,0.45) with backdrop-filter blur(20px)
- Toolbar/sidenav: semi-transparent with blur
- Dialogs: translucent glass with frosted backdrop
- Paginators, dropdowns, datepickers: glass-themed
- Color palette: #1a3a5c (dark), #3a6bb5/#5b8fd9 (primary blue)

### Key Frontend Services

| Service | Key Methods |
|---------|-------------|
| `AuthService` | login(), selectCompany(), switchCompany(), logout(), getCurrentUser() |
| `TokenService` | getAccessToken(), setTokens(), getUserData(), clearTokens() |
| `MenuService` | loadUserMenu(), hasPermission(menuName, action), clearMenu() |
| `ApiService` | get<T>(), post<T>(), put<T>(), delete<T>() |
| `NotificationService` | success(), error(), info() |
| `CompanyContextService` | switchCompany() (triggers menu reload) |

---

## 5. High-Level Flows

### 5.1 Authentication Flow

```
User enters credentials
  -> POST /auth/login
  -> Returns tempToken + companies[]
  -> If single company: auto-select
  -> If multiple: show company picker
  -> POST /auth/select-company (with tempToken)
  -> Returns accessToken + refreshToken + user context
  -> Store in localStorage
  -> Navigate to /dashboard
  -> Load menu tree (GET /menus/user-tree)
  -> Render sidebar based on role permissions
```

### 5.2 Company Switching Flow

```
User selects company from switcher dropdown
  -> POST /auth/switch-company
  -> New JWT issued with new company_id/role_id
  -> Tokens updated in localStorage
  -> Menu tree reloaded for new company/role
  -> All data-bound components refresh
```

### 5.3 Enquiry -> Costing -> Quotation Flow

```
1. Create Enquiry (customer, date, mode, description)
2. Add Enquiry Details (line items: grade, dia, length, unit)
3. Add Costing per line item:
   - Auto-fill TP cost from RawMaterialCost (by diameter)
   - Fill 20 cost points + basicRate + GST + EXFORPrice
   - Create new costing version when needed
4. Create Quotation (linked to enquiry)
   - Add QuotDetails (grade, dia, quantity, rates, GST breakdown)
   - Add Terms & Conditions (from master or custom)
5. Quotation Versioning:
   - "Revise" creates new QuotSummary (versionNo+1, parentQuotId)
   - Copies details and T&C to new version
   - quotNo gets revision suffix: QUOT-001-R1, QUOT-001-R2
   - Previous versions become read-only
6. Approval:
   - PUT /quotations/{id}/approve
   - Sets status=Approved, approvedby, approvedon
7. Print specific version via /quotations/{id}/print
```

### 5.4 Permission Flow

```
1. Admin creates Role (RoleMaster)
2. Admin assigns menu permissions via Role-Menu Mapping UI:
   - Tree view of all menus
   - Per-node CRUD checkboxes (CanAdd, CanRead, CanEdit, CanDelete)
   - Parent toggle applies to all children
3. Admin maps User to Role+Company (UserRoleMap)
4. On login, JWT contains role_id
5. GET /menus/user-tree filters menus by CanRead=true
6. Frontend *appHasPermission directive hides/shows UI elements
7. Backend require_permission() dependency validates per-endpoint
```

### 5.5 New Company Setup Flow

```
Super Admin creates company via POST /companies
  -> company_setup_service.seed_company_defaults():
     - Creates default menu tree (24 items matching frontend routes)
     - Creates "Admin" role with full CRUD on all menus
  -> Admin can then create users and assign roles for the company
```

### 5.6 Email Flow

```
1. Super Admin configures SMTP (MailFrom, MailPassword, SMTP, PortNo) in Company settings
2. User selects a quotation and a customer contact
3. POST /email/send-quotation { quotId, contactId, subject?, htmlBody? }
4. Backend fetches SMTP config from Company table
5. Resolves contact email (personalEmail or officeEmail)
6. Sends email via STARTTLS-authenticated SMTP
7. Optional: Test SMTP with POST /email/test-smtp
```

---

## 6. Known Bugs & Issues

### Critical

1. **No `POST /auth/change-password` endpoint on backend**
   - Frontend ProfileDialogComponent calls `POST /auth/change-password`
   - This endpoint does not exist in `backend/app/api/v1/auth.py`
   - Change password will fail with 404

### Functional Issues

2. **Hardcoded GSTIN in Quotation Print**
   - `quotation-print.component.ts` line ~91 has `GSTIN: 27XXXXX1234Z1`
   - Should pull from Company master data dynamically

3. **CustomerSite missing `city` column in model**
   - `CustomerSite` model has `state`, `dist`, `PIN` but no `city` column
   - May need `city` field depending on business requirements

4. **Enquiry status values inconsistent**
   - Backend model default: `"Open"`
   - Frontend filter options: `DRAFT, SUBMITTED, APPROVED, REJECTED, CLOSED`
   - May cause mismatches on status filtering

5. **No AuthGuard applied to routes**
   - `app.routes.ts` does not apply `authGuard` to the main layout route
   - The guard exists (`auth.guard.ts`) but is not wired into routing
   - Unauthenticated users can navigate to protected routes (interceptor will 401 on API calls)

### UI/UX Issues

6. **Mixed template syntax (legacy vs modern)**
   - Some components use `*ngIf` / `*ngFor` (legacy)
   - Others use `@if` / `@for` (Angular 17+ control flow)
   - Not a bug but inconsistent

7. **Build budget warning**
   - `quotation-print.component.ts` exceeds 4.00 kB component style budget by 67 bytes
   - Non-blocking but shows in every build output

8. **Profile avatar positioning**
   - Profile avatar button in toolbar may have shadow offset issues due to `mat-icon-button` internal sizing
   - The 48x48 touch target vs 36x36 avatar can cause visual misalignment

### Missing Features (Not Yet Implemented)

9. **Asset upload UI**
   - `AssetUploadComponent` exists but appears to be a minimal placeholder
   - No route defined for `/assets` in `app.routes.ts`

10. **No global error handling**
    - Each component handles API errors individually
    - No centralized error handler beyond 401 -> logout in interceptor

11. **Permission directive not widely applied**
    - `HasPermissionDirective` exists but not visibly used in most list components
    - Add/Edit/Delete buttons are shown to all users regardless of permissions

12. **No pagination on server side**
    - All list endpoints return full datasets
    - Pagination is client-side only (MatTableDataSource)
    - May cause performance issues with large datasets

---

*Generated: 2026-03-29*
