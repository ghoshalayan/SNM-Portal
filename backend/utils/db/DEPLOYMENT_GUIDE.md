# SNM Portal - Database Deployment & Management Guide

## Table of Contents
1. [Overview](#overview)
2. [File Index](#file-index)
3. [Fresh Deployment (New Server)](#fresh-deployment-new-server)
4. [Alembic Migration Workflow](#alembic-migration-workflow)
5. [Manual SQL Deployment (Without Alembic)](#manual-sql-deployment-without-alembic)
6. [Environment Configuration](#environment-configuration)
7. [Login Credentials](#login-credentials)
8. [Schema Reference](#schema-reference)
9. [Common Operations](#common-operations)
10. [Troubleshooting](#troubleshooting)

---

## Overview

| Component       | Technology                                |
|-----------------|-------------------------------------------|
| Database        | SQL Server (local dev or Azure SQL)       |
| ORM             | SQLAlchemy 2.x                            |
| Migrations      | Alembic                                   |
| Driver          | pyodbc (ODBC Driver 18 for SQL Server)    |
| Password Hash   | bcrypt via passlib                        |

**Database name:** `SNMPortal` (configurable via `.env`)

---

## File Index

```
backend/
├── utils/db/
│   ├── DEPLOYMENT_GUIDE.md        ← This file
│   ├── 001_schema.sql             ← Full DDL: all 27 tables in FK-safe order
│   ├── 002_seed_data.sql          ← Seed: company, roles, users, menus, permissions
│   ├── 003_rollback.sql           ← Drop all tables in reverse FK order
│   └── alembic_commands.md        ← Quick-reference for Alembic CLI
├── alembic/
│   ├── env.py                     ← Alembic environment config
│   ├── script.py.mako             ← Migration template
│   └── versions/
│       ├── 9eaf9699f05f_initial_schema_all_25_tables.py
│       └── e88c297e3e9d_seed_superadmin_test_user_company_menus_.py
├── alembic.ini                    ← Alembic config (reads DB URL from .env)
└── .env                           ← DB_CONNECTION_STRING, JWT_SECRET_KEY, etc.
```

---

## Fresh Deployment (New Server)

### Option A: Using Alembic (Recommended)

Alembic tracks migration state in the `alembic_version` table, so you always know which migrations have been applied.

```bash
# 1. Create the database on SQL Server
#    (SSMS or sqlcmd)
#    CREATE DATABASE SNMPortal;

# 2. Configure .env with your connection string
#    See "Environment Configuration" section below

# 3. Activate virtual environment
cd backend
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# 4. Install dependencies (if not already done)
pip install -r requirements.txt

# 5. Run all migrations (schema + seed data)
alembic upgrade head

# 6. Verify
alembic current
# Should show: f3a1b2c4d5e6 (head)
```

### Option B: Using Raw SQL (Without Python)

For DBA-managed environments or servers without Python:

```sql
-- 1. Create database
CREATE DATABASE SNMPortal;
GO
USE SNMPortal;
GO

-- 2. Run schema creation
-- Execute: utils/db/001_schema.sql

-- 3. Run seed data
-- Execute: utils/db/002_seed_data.sql
```

> **Note:** If using Option B, Alembic will not track the migration state. If you later switch to Alembic, run:
> ```bash
> alembic stamp head
> ```
> This tells Alembic the database is already at the latest migration without re-running anything.

---

## Alembic Migration Workflow

### Check Current State
```bash
# Show current migration version
alembic current

# Show migration history
alembic history --verbose
```

### Creating a New Migration

When you change a SQLAlchemy model (add column, new table, etc.):

```bash
# 1. Auto-generate migration from model changes
alembic revision --autogenerate -m "Add xyz column to CustomerMaster"

# 2. REVIEW the generated file in alembic/versions/
#    Auto-generated migrations may miss or misdetect changes.
#    Always verify the upgrade() and downgrade() functions.

# 3. Apply the migration
alembic upgrade head
```

### Creating a Data-Only Migration (Seed/Patch)

```bash
# 1. Create empty migration
alembic revision -m "Seed new delivery modes"

# 2. Edit the file — write INSERT/UPDATE statements in upgrade()
# 3. Apply
alembic upgrade head
```

### Rolling Back

```bash
# Roll back 1 migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade 9eaf9699f05f

# Roll back everything (empty database)
alembic downgrade base
```

### Migration Chain

```
(empty) → 9eaf9699f05f (schema) → e88c297e3e9d (seed data) → f3a1b2c4d5e6 (fix menu URLs) → [future migrations]
```

---

## Manual SQL Deployment (Without Alembic)

For production environments managed by DBAs:

| Step | File | Purpose |
|------|------|---------|
| 1 | `001_schema.sql` | Creates all 27 tables with FKs, indexes, defaults |
| 2 | `002_seed_data.sql` | Inserts company, roles, users, menus, permissions |
| 3 | `003_rollback.sql` | **DANGER:** Drops everything. Dev/test only. |

Execute in order using SSMS, sqlcmd, or Azure Data Studio:

```bash
# sqlcmd example
sqlcmd -S localhost -d SNMPortal -U budu -P "Pass*2026" -i utils/db/001_schema.sql
sqlcmd -S localhost -d SNMPortal -U budu -P "Pass*2026" -i utils/db/002_seed_data.sql
```

---

## Environment Configuration

### .env File (backend/.env)

```ini
# Database
DB_CONNECTION_STRING=mssql+pyodbc://USER:PASSWORD@HOST/SNMPortal?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=no

# JWT
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Azure Blob Storage (optional - for file uploads)
AZURE_BLOB_CONNECTION_STRING=
AZURE_BLOB_CONTAINER=snm-assets

# CORS
CORS_ORIGINS=http://localhost:4200
```

### Connection String Examples

| Environment | Connection String |
|-------------|-------------------|
| Local Dev | `mssql+pyodbc://budu:Pass*2026@localhost/SNMPortal?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=no` |
| Azure SQL | `mssql+pyodbc://adminuser:P@ssw0rd@snm-server.database.windows.net/SNMPortal?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no` |
| Windows Auth | `mssql+pyodbc://@localhost/SNMPortal?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes` |

---

## Login Credentials

| User | Login | Password | Role | Permissions |
|------|-------|----------|------|-------------|
| Super Administrator | `admin` | `Admin@123` | Super Admin | Full CRUD on all 25 menus |
| Test User | `testuser` | `Test@123` | Standard User | Read: Dashboard, Customers. Full CRUD: Enquiries, Quotations, Assets |

> **IMPORTANT:** Change these passwords immediately after first deployment to production.

To generate a new bcrypt hash:
```python
from passlib.context import CryptContext
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
print(pwd.hash("YourNewPassword"))
```

---

## Schema Reference

### Table Count: 27

| Category | Tables | Count |
|----------|--------|-------|
| Core | Company, UserMaster, UserRoleMap, RoleMaster, MenuMaster, RoleMenuMap | 6 |
| Items | ItemGrade, ItemName, ItemLength, ItemSize | 4 |
| Delivery | DeliveryTerm, DeliveryMode | 2 |
| Masters | ContactType, CostPointMaster, CustomerClassification, TermsNConditionMaster, RawMaterialCost | 5 |
| Customers | CustomerMaster, CustomerContacts, CustomerSite | 3 |
| Enquiries | CustomerEnquiry, CustomerEnquiryDetails, CustomerEnquiryCosting | 3 |
| Quotations | QuotSummary, QuotDetails, QuotTermsNConditions | 3 |
| Assets | Asset | 1 |

### Common Patterns Across All Tables

- **Soft Delete:** `isActive BIT NOT NULL DEFAULT 1` — never hard-delete rows
- **Audit Fields:** `createdon`, `createdby`, `lastupdateon`, `lastupdateby`
- **Multi-Tenancy:** `companyId INT NOT NULL REFERENCES Company(companyId)` on every table
- **Auto-Increment PKs:** All primary keys are `INT IDENTITY(1,1)`

### Versioning

| Table | Versioning Column | Grouping |
|-------|------------------|----------|
| CustomerEnquiryCosting | `versionNo` (default 1) | Per `enqid` + `enqdtlid` |
| QuotSummary | `versionNo` (default 1), `parentQuotId` | `parentQuotId` links revisions |

### Menu Tree Structure

```
MenuMaster.parentMenuId → MenuMaster.menuId  (self-referencing)

Dashboard
Administration/
├── Company Management
├── User Management
├── Role Management
└── Role-Menu Mapping
Masters/
├── Item Grade
├── Item Name
├── Item Length
├── Item Size
├── Delivery Term
├── Delivery Mode
├── Contact Type
├── Customer Classification
├── Cost Point
├── Terms & Conditions
└── Raw Material Cost
Customers/
└── Customer List
Enquiries/
└── Enquiry List
Quotations/
└── Quotation List
Assets
```

---

## Common Operations

### Add a New Company
```sql
INSERT INTO Company (companyName, companyCode, city, state, country, isActive, createdon, createdby)
VALUES ('New Company', 'NEWCO', 'Delhi', 'Delhi', 'India', 1, GETDATE(), 1);
```
Then create roles, users, and copy the menu tree for the new company.

### Add a New Menu Item
```sql
-- Find the parent menu ID
SELECT menuId, menuName FROM MenuMaster WHERE menuName = 'Masters';

-- Insert child menu
INSERT INTO MenuMaster (companyId, menuName, menuUrl, menuIcon, parentMenuId, menuOrder, isActive, createdon, createdby)
VALUES (1, 'New Master', '/masters/new-master', 'star', /* parentMenuId */ 7, 12, 1, GETDATE(), 1);

-- Grant permission to Super Admin role
INSERT INTO RoleMenuMap (roleId, menuId, CanAdd, CanRead, CanEdit, CanDelete, isActive, createdon, createdby)
VALUES (1, SCOPE_IDENTITY(), 1, 1, 1, 1, 1, GETDATE(), 1);
```

### Reset a User Password
```python
# Run in Python with venv activated
from app.core.security import hash_password
new_hash = hash_password("NewPassword@123")
print(new_hash)  # Use this in the UPDATE statement below
```
```sql
UPDATE UserMaster SET userPassword = '<bcrypt_hash>' WHERE userLogin = 'admin';
```

### Check Migration Status
```bash
alembic current       # Current revision
alembic history       # Full history
alembic heads         # Latest available
```

---

## Troubleshooting

### "No module named 'pyodbc'"
The virtual environment is not activated. Run:
```bash
cd backend
venv\Scripts\activate    # Windows
pip install pyodbc
```

### "Login failed for user"
Check `.env` → `DB_CONNECTION_STRING`. Verify username/password and that the database exists:
```sql
SELECT name FROM sys.databases WHERE name = 'SNMPortal';
```

### "ODBC Driver 18 for SQL Server not found"
Install the driver from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

### Alembic "Target database is not up to date"
```bash
# Check what's pending
alembic current
alembic heads

# Apply pending migrations
alembic upgrade head
```

### Alembic "Can't locate revision"
The `alembic_version` table references a revision that doesn't exist in `alembic/versions/`. Fix:
```bash
# Option 1: Stamp to the current head
alembic stamp head

# Option 2: Reset (caution - only if DB schema matches)
alembic stamp base
alembic upgrade head
```

### "Table already exists" on fresh deploy
The database already has tables. Either:
1. Drop everything first: run `003_rollback.sql`
2. Or stamp Alembic to skip: `alembic stamp head`

### Azure SQL: Encryption errors
Add `Encrypt=yes&TrustServerCertificate=no` to connection string. For dev, use `Encrypt=no`.
