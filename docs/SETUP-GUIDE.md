# SNM Portal - Setup Guide

## Prerequisites

- **Python** 3.11+
- **Node.js** 18+ and npm
- **SQL Server** (local instance or Azure SQL)
- **ODBC Driver 17 for SQL Server** ([download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server))
- **Git**

---

## 1. Clone & Structure

```
SNM-portal/
├── backend/      # FastAPI + SQLAlchemy + Alembic
├── frontend/     # Angular 21 + Material
└── docs/         # This documentation
```

---

## 2. Backend Setup

### 2.1 Create Virtual Environment

```bash
cd backend
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash
# venv\Scripts\activate        # Windows CMD
# source venv/bin/activate     # Linux/Mac
```

### 2.2 Install Dependencies

```bash
pip install -r requirements.txt
```

**Key dependencies:**
| Package            | Version  | Purpose                    |
|--------------------|----------|----------------------------|
| fastapi            | 0.115.6  | Web framework              |
| uvicorn            | 0.34.0   | ASGI server                |
| sqlalchemy         | 2.0.36   | ORM                        |
| pyodbc             | 5.2.0    | SQL Server driver          |
| alembic            | 1.14.1   | Database migrations        |
| python-jose        | 3.3.0    | JWT tokens                 |
| passlib + bcrypt   | 1.7.4    | Password hashing           |
| pydantic-settings  | 2.7.1    | Config from .env           |
| azure-storage-blob | 12.24.0  | Azure Blob Storage         |
| aiosmtplib         | 3.0.2    | Async email                |

### 2.3 Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```ini
# Required
DB_CONNECTION_STRING=mssql+pyodbc://sa:YourPassword@localhost:1433/SNMPortal?driver=ODBC+Driver+17+for+SQL+Server
JWT_SECRET_KEY=change-this-to-a-secure-random-string

# Optional
AZURE_BLOB_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...
AZURE_BLOB_CONTAINER=snm-assets
CORS_ORIGINS=http://localhost:4200
DEBUG=true
```

### 2.4 Create Database

Create the `SNMPortal` database in SQL Server before running migrations:

```sql
CREATE DATABASE SNMPortal;
```

### 2.5 Run Migrations

```bash
python -m alembic upgrade head
```

This creates all tables and seeds:
- Test company "SNM Steel Corp"
- SuperAdmin user (`admin` / `Admin@123`)
- Test user (`testuser` / `Test@123`)
- Full menu tree with role permissions

### 2.6 Start Backend Server

```bash
uvicorn app.main:app --reload --port 8000
```

- API docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## 3. Frontend Setup

### 3.1 Install Dependencies

```bash
cd frontend
npm install
```

**Key dependencies:**
| Package           | Version | Purpose                   |
|-------------------|---------|---------------------------|
| @angular/core     | ^21.2.0 | Angular framework         |
| @angular/material | ^21.2.4 | UI components             |
| dagre             | ^0.8.5  | Org tree graph layout     |
| rxjs              | ~7.8.0  | Reactive programming      |

### 3.2 Proxy Configuration

`proxy.conf.json` routes `/api` requests to the backend:

```json
{
  "/api": {
    "target": "http://localhost:8000",
    "secure": false,
    "changeOrigin": true
  }
}
```

### 3.3 Start Frontend Dev Server

```bash
npm start
# or: ng serve
```

- App: http://localhost:4200
- Auto-proxies API calls to http://localhost:8000

---

## 4. Login Credentials (Seeded)

| User       | Login      | Password   | Role       |
|------------|------------|------------|------------|
| Admin      | admin      | Admin@123  | SuperAdmin |
| Test User  | testuser   | Test@123   | Staff      |

---

## 5. API Endpoints Overview

Base URL: `/api/v1`

| Prefix        | Tag                | Description                      |
|---------------|--------------------|----------------------------------|
| /auth         | Authentication     | Login, refresh, switch company   |
| /companies    | Companies          | Company CRUD                     |
| /users        | Users              | User CRUD + role mappings        |
| /roles        | Roles              | Role CRUD                        |
| /menus        | Menus              | Menu tree CRUD                   |
| /masters      | Masters            | All master data CRUD             |
| /customers    | Customers          | Customer + contacts + sites      |
| /enquiries    | Enquiries          | Enquiry + details + costing      |
| /quotations   | Quotations         | Quotation + details + T&C        |
| /assets       | Assets             | File upload/download (Azure)     |
| /email        | Email              | Send email via company SMTP      |
| /org-tree     | Organization Tree  | Org tree view + assign/unassign  |

---

## 6. Frontend Routes

| Path                          | Component              |
|-------------------------------|------------------------|
| /login                        | LoginComponent         |
| /dashboard                    | DashboardComponent     |
| /companies                    | CompanyListComponent   |
| /users                        | UserListComponent      |
| /roles                        | RoleListComponent      |
| /roles/:roleId/menu-mapping   | RoleMenuMappingComponent |
| /org-tree                     | OrgTreeComponent       |
| /masters/item-grades          | ItemGradeListComponent |
| /masters/item-names           | ItemNameListComponent  |
| /masters/item-lengths         | ItemLengthListComponent |
| /masters/item-sizes           | ItemSizeListComponent  |
| /masters/delivery-terms       | DeliveryTermListComponent |
| /masters/delivery-modes       | DeliveryModeListComponent |
| /masters/contact-types        | ContactTypeListComponent |
| /masters/customer-classifications | CustomerClassificationListComponent |
| /masters/cost-points          | CostPointListComponent |
| /masters/terms-conditions     | TermsConditionListComponent |
| /masters/raw-material-costs   | RawMaterialCostListComponent |
| /masters/countries            | CountryListComponent   |
| /masters/states               | StateListComponent     |
| /masters/districts            | DistrictListComponent  |
| /masters/dia-masters          | DiaMasterListComponent |
| /customers                    | CustomerListComponent  |
| /customers/new                | CustomerFormComponent  |
| /customers/:id/edit           | CustomerFormComponent  |
| /enquiries                    | EnquiryListComponent   |
| /enquiries/new                | EnquiryFormComponent   |
| /enquiries/:id/edit           | EnquiryFormComponent   |
| /quotations                   | QuotationListComponent |
| /quotations/new               | QuotationFormComponent |
| /quotations/:id/edit          | QuotationFormComponent |
| /quotations/:id/print         | QuotationPrintComponent |

---

## 7. Architecture Notes

- **Multi-tenancy:** Every API query is filtered by `companyId` from JWT
- **Auth flow:** Login -> get companies list -> select company -> JWT issued with `{user_id, company_id, role_id}`
- **Soft delete:** All records use `isActive` flag, never hard-deleted
- **Standalone components:** Angular 21 with no NgModules, all lazy-loaded
- **Permission system:** `RoleMenuMap` controls CRUD access per menu per role; `*hasPermission` directive in frontend
