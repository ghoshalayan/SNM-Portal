# SNM Portal - Alembic Migrations

## Migration Chain

```
(base)
  |
  v
9eaf9699f05f  Initial schema - all 25 tables
  |
  v
e88c297e3e9d  Seed superadmin, test user, company, menus, permissions
  |
  v
f3a1b2c4d5e6  Fix menu URLs from singular to plural
  |
  v
a1b2c3d4e5f6  Add Country, StateMaster, DistrictMaster, DiaMaster tables
  |
  v
b2c3d4e5f6a7  Add Country/State/District/Dia Master menus and permissions
  |
  v
c3d4e5f6a7b8  Remove Role-Menu Mapping submenu (soft-delete)
  |
  v
d4e5f6a7b8c9  Add Organization Tree menu under Administration
```

---

## Migration Details

### 1. `9eaf9699f05f` — Initial Schema
- **Date:** 2026-03-28
- **Revises:** None (first migration)
- **Action:** Creates all 25 original tables (Company, UserMaster, UserRoleMap, RoleMaster, MenuMaster, RoleMenuMap, ItemGrade, ItemName, ItemLength, ItemSize, DeliveryTerm, DeliveryMode, CustomerClassification, ContactType, CostPointMaster, CustomerMaster, CustomerContacts, CustomerSite, CustomerEnquiry, CustomerEnquiryDetails, CustomerEnquiryCosting, QuotSummary, QuotDetails, QuotTermsNConditions, TermsNConditionMaster, RawMaterialCost, Asset)
- **Downgrade:** Drops all tables in reverse dependency order

### 2. `e88c297e3e9d` — Seed Data
- **Date:** 2026-03-28
- **Revises:** `9eaf9699f05f`
- **Action:** Seeds initial data:
  - Test company: "SNM Steel Corp"
  - SuperAdmin user: login `admin`, password `Admin@123`
  - Test user: login `testuser`, password `Test@123`
  - SuperAdmin role with `IsSuperAdmin = True`
  - Staff role
  - Full menu tree (Dashboard, Administration, Masters, Customers, Enquiries, Quotations, Assets)
  - Full CRUD permissions for SuperAdmin on all menus
  - Read-only permissions for Staff on Dashboard, Masters, Customers
  - UserRoleMap entries for both users
- **Downgrade:** Deletes seeded data in reverse order

### 3. `f3a1b2c4d5e6` — Fix Menu URLs
- **Date:** 2026-03-28
- **Revises:** `e88c297e3e9d`
- **Action:** Updates `MenuMaster.menuUrl` from singular to plural to match frontend routes:
  - `/masters/item-grade` -> `/masters/item-grades`
  - `/masters/item-name` -> `/masters/item-names`
  - `/masters/delivery-term` -> `/masters/delivery-terms`
  - ... (all master menu URLs)
- **Downgrade:** Reverts URLs back to singular form

### 4. `a1b2c3d4e5f6` — New Location/Dia Tables
- **Date:** 2026-03-29
- **Revises:** `f3a1b2c4d5e6`
- **Action:** Creates 4 new tables:
  - `Country` (countryid, countryname)
  - `StateMaster` (stateid, StateName, Country)
  - `DistrictMaster` (districtid, districName, StateName, Country)
  - `DiaMaster` (diaid, itemid FK->ItemName, diadescription, companyId FK->Company)
- **Downgrade:** Drops the 4 tables

### 5. `b2c3d4e5f6a7` — New Master Menus
- **Date:** 2026-03-29
- **Revises:** `a1b2c3d4e5f6`
- **Action:** Adds menu entries under "Masters" for the 4 new tables:
  - Country (`/masters/countries`, icon: `public`)
  - State (`/masters/states`, icon: `map`)
  - District (`/masters/districts`, icon: `location_city`)
  - Dia Master (`/masters/dia-masters`, icon: `radio_button_unchecked`)
  - Grants full CRUD permissions to SuperAdmin role
- **Downgrade:** Soft-deletes the menu entries and RoleMenuMap records

### 6. `c3d4e5f6a7b8` — Remove Role-Menu Mapping Submenu
- **Date:** 2026-03-30
- **Revises:** `b2c3d4e5f6a7`
- **Action:** Soft-deletes the "Role-Menu Mapping" menu entry from sidebar (accessed from within Role Management instead)
- **Downgrade:** Re-activates the menu entry

### 7. `d4e5f6a7b8c9` — Add Organization Tree Menu
- **Date:** 2026-03-30
- **Revises:** `c3d4e5f6a7b8`
- **Action:** For each active company:
  - Finds "Administration" parent menu
  - Inserts "Organization Tree" child menu (`/org-tree`, icon: `account_tree`)
  - Grants permissions to all roles that have "Role Management" access
  - Idempotent (skips if already exists)
- **Downgrade:** Soft-deletes Organization Tree menu and RoleMenuMap entries

---

## Running Migrations

```bash
# Navigate to backend
cd backend

# Activate virtual environment
source venv/Scripts/activate   # Windows Git Bash
# or: venv\Scripts\activate    # Windows CMD
# or: source venv/bin/activate # Linux/Mac

# Run all pending migrations
python -m alembic upgrade head

# Check current revision
python -m alembic current

# View migration history
python -m alembic history --verbose

# Downgrade one step
python -m alembic downgrade -1

# Downgrade to specific revision
python -m alembic downgrade 9eaf9699f05f
```

## Configuration

- `alembic.ini` — `script_location = alembic`, URL set dynamically from `.env`
- `alembic/env.py` — Reads `DB_CONNECTION_STRING` from `.env`, imports all models from `app.models`
