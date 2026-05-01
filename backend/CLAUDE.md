# SNM Portal - Backend

## Overview
Multi-tenant B2B portal backend for managing customers, enquiries, quotations, and costing with role-based access.

**Stack:** FastAPI 0.115.6 | SQLAlchemy 2.0 | SQL Server (pyodbc) | Alembic | JWT Auth | Azure Blob Storage

## Quick Start
```bash
cd backend
pip install -r requirements.txt
# Copy .env.example to .env and fill in values
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Project Structure
```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, health check
│   ├── core/
│   │   ├── config.py            # pydantic-settings, loads from .env
│   │   ├── database.py          # SQLAlchemy engine + SessionLocal
│   │   ├── security.py          # JWT encode/decode, bcrypt hashing
│   │   ├── dependencies.py      # get_db, get_current_user, require_permission
│   │   └── email.py             # SMTP email utility
│   ├── models/                  # SQLAlchemy ORM (25 tables)
│   │   └── base.py              # AuditMixin: createdon, createdby, lastupdateon, lastupdateby, isActive
│   ├── schemas/                 # Pydantic v2 request/response models
│   ├── services/                # Business logic (pure functions, not classes)
│   └── api/v1/                  # Route handlers
│       └── router.py            # Aggregates all routers under /api/v1
├── alembic/                     # Migrations (7 applied)
├── requirements.txt
├── .env                         # Secrets (DO NOT COMMIT)
└── .env.example
```

## Architecture Patterns

### Authentication Flow
1. `POST /api/v1/auth/login` - validates credentials, returns temp token + company list
2. `POST /api/v1/auth/select-company` - exchanges temp token for JWT pair (access + refresh)
3. JWT payload: `{ user_id, company_id, role_id, is_super_admin, type, exp }`
4. Access token: 30 min, Refresh token: 7 days
5. `POST /api/v1/auth/switch-company` - re-issues JWT with different company context

### Multi-Tenancy
- **Company** is the tenant boundary. All business entities have `companyId` FK.
- Every query MUST filter by `current_user.company_id` from the JWT.
- Users can belong to multiple companies via `UserRoleMap` (different role per company).
- SuperAdmin (`Role.IsSuperAdmin=True`) can access any company.

### Access Control (RBAC v2)

**Unified service:** `services/access_service.py` exposes the `AccessContext`
dependency that encapsulates the full access pipeline. All business endpoints
route through this to stay consistent.

**The 7-filter pipeline** (fail-fast, short-circuit on first failure):

| # | Filter | What it does |
|---|---|---|
| F1 | Auth | JWT validation (via `get_current_user`) |
| F2 | Company | Multi-tenant isolation (`apply_company_filter`) |
| F3 | Menu Permission | `RoleMenuMap` flag check (`require_permission`) |
| F4 | Parent Visibility | For sub-resources: parent must pass F2/F5/F6 (`require_parent_visible`) |
| F5 | Hierarchy | `ownerUserId ∈ visible_user_ids` (BFS on `UserRoleMap.reportTo`) |
| F6 | Location | Record's state/dist in user's `UserLocationMap` |
| F7 | Business Rule | Entity-specific (FY exists, status transitions, uniques, etc.) |

**Bypass matrix:**

| Role type | F2 | F3 | F4 | F5 | F6 |
|---|:-:|:-:|:-:|:-:|:-:|
| SuperAdmin (`IsSuperAdmin=True`) | bypass | bypass | bypass | bypass | bypass |
| CompanyAdmin (`IsCompanyAdmin=True`) | required | required | required | bypass | bypass |
| Others | required | required | required | required | required |

**Role flags** (all on `RoleMaster`, fully dynamic — no role-name checks in code):

| Flag | Purpose |
|---|---|
| `IsSuperAdmin` | Bypasses everything except F1/F7 |
| `IsCompanyAdmin` | Bypasses F5 and F6 (full access within one company) |
| `numGenMode` | `own_code` \| `parent_code` \| `select_code` — owner resolution |
| `downwardLevels` | N levels of children visible (`-1` = unlimited) |
| `upwardLevels` | N levels of parents visible (`0` = none, `-1` = unlimited) |
| `includeSubtreeOnUpward` | When walking up, also include each ancestor's subtree |
| `peerAccess` | See siblings (same reportTo) |
| `peerSubtree` | If peerAccess=T, also include peers' subtrees |
| `locationScopeRequired` | If False → bypass F6 |
| `enforceChildLocationSubset` | KRO-style: user's locations ⊆ reportTo's locations |

**Menu permission flags** (on `RoleMenuMap`):
- Core: `CanAdd`, `CanRead`, `CanEdit`, `CanDelete`
- Extended: `CanEditNumber`, `CanApprove`, `CanRevise`,
  `CanTransferOwnership`, `CanGenerateUnderOthers`
- Extended flags are only meaningful for certain menus (e.g. Approve/Revise for Quotations).
  The `MENU_EXTRA_PERMS` map in the frontend controls which are shown per menu.

**Ownership handover:**
- `POST /enquiries/{id}/handover` and `POST /quotations/{id}/handover`
- Requires `CanTransferOwnership` permission
- Target user must be in initiator's `visible_user_ids`
- Quotation handover auto-reverts status `Approved → Draft` so the new owner re-approves

**KRO location subset & cascade:**
- On role assignment (`POST /users/{id}/role-mappings`): if target user's role has
  `enforceChildLocationSubset=True`, auto-inherit reportTo's full location set.
- On location assignment (`POST /users/{id}/location-mappings`): validate new
  locations ⊆ reportTo's locations; cascade-narrow any subordinates.
- Cascades are visibility-only (records are preserved, just filtered out of lists).

**Role templates** (seeded idempotently by migration `g1h2i3j4k5l6`):
`SuperAdmin`, `CompanyAdmin`, `Director`, `HOD`, `KRO` —
created per company with sensible default flags + menu permissions.
Admins can customize after seeding; re-running the migration is safe.

### Per-Module Coverage

| Module | F2 | F3 | F4 | F5 | F6 |
|---|:-:|:-:|:-:|:-:|:-:|
| Customers (master) | ✅ | ✅ | — | — | — |
| Customer Contacts | ✅ | ✅ | — | — | ✅ |
| Customer Sites | ✅ | ✅ | — | — | ✅ |
| Enquiries | ✅ | ✅ | — | ✅ | ✅ |
| Enquiry sub-resources | ✅ | ✅ | inherit | inherit | inherit |
| Quotations | ✅ | ✅ | — | ✅ | ✅ |
| Quotation sub-resources | ✅ | ✅ | inherit | inherit | inherit |
| Communication Logs | ✅ | ✅ | — | ✅ | — |

### Permission System
- `RoleMenuMap` stores per-role CRUD flags per menu; access_service's
  `require_permission(menu, action, ctx)` is the preferred API.
- Legacy `require_permission` dependency in `core/dependencies.py` still works
  but is being phased out in favor of `ctx.has_permission()`.
- Menus are a self-referencing tree (`MenuMaster.parentMenuId`).

### Service Layer
- Business logic lives in `app/services/` as plain functions (not classes)
- Route handlers call services; services call DB
- `company_setup_service.py` seeds 45 default menus + permissions when a new company is created

### Soft Delete
- All models use `isActive` flag. DELETE endpoints set `isActive=False`, never hard-delete.
- AuditMixin provides `createdon`, `createdby`, `lastupdateon`, `lastupdateby` on all models.

### Versioning (Quotations & Costing)
- `QuotSummary.versionNo` incremented on revision; `parentQuotId` links to original
- `CustomerEnquiryCosting.versionNo` incremented per costing revision
- Latest version = `MAX(versionNo)` per parent entity
- Previous versions are read-only

## API Routes
```
/api/v1/auth          - Login, select-company, switch-company, refresh, my-companies
/api/v1/companies     - Company CRUD (super admin only)
/api/v1/users         - User CRUD + /users/{id}/role-mappings
/api/v1/roles         - Role CRUD
/api/v1/menus         - Menu tree + role-menu permissions
/api/v1/masters       - All master data (item-grade, delivery-term, cost-point, etc.)
/api/v1/customers     - Customer CRUD + /contacts, /sites sub-resources
/api/v1/enquiries     - Enquiry CRUD + details + costing
/api/v1/quotations    - Quotation CRUD + details + TNC + versioning + print
/api/v1/org-tree      - Organization hierarchy management
/api/v1/assets        - File upload/download (Azure Blob)
/api/v1/email         - Email sending
/health               - Health check
/docs                 - Swagger UI
/redoc                - ReDoc
```

## Database
- **25 tables** defined in `app/models/`
- Column naming is **camelCase** (e.g., `companyId`, `userId`, `customerId`)
- Some legacy inconsistencies: `diaid`, `enqid`, `enqdtlid` (no camelCase)
- Alembic migrations in `alembic/versions/` (run with `alembic upgrade head`)
- Migration `e88c297e3e9d` seeds test data (superadmin user, test company, menus)

## Environment Variables (.env)
```
DB_CONNECTION_STRING=mssql+pyodbc://user:pass@host:1433/SNMPortal?driver=ODBC+Driver+17+for+SQL+Server
JWT_SECRET_KEY=<strong-random-key>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
AZURE_BLOB_CONNECTION_STRING=<azure-connection-string>
AZURE_BLOB_CONTAINER=snm-assets
CORS_ORIGINS=http://localhost:4200
DEBUG=false
```

## Known Loopholes & Issues

### Security
1. **SMTP passwords stored in plaintext** in `Company` table (`MailPassword` column) - should use encryption or vault
2. **No rate limiting** - brute-force login attacks possible - # Fix Done
<!-- 3. **No HTTPS enforcement** - CORS allows http://localhost:4200
4. **JWT secret in .env.example** is a weak placeholder - no minimum-length validation -->
5. **Test data seeded in migration** - `e88c297e3e9d` seeds a test user/company; could create duplicates or leak in prod

### Data Integrity
<!-- 6. **Org-tree visibility not applied everywhere** - `/customers`, `/users`, `/masters` routes don't call `get_visible_user_ids()`. A user can see all company customers, not just their team's. -->
7. **No pagination** - all list endpoints return ALL records. Will break with large datasets. -- # Fix Done
8. **No validation on company access** - user creation doesn't verify `companyId` exists before assigning - # Fix Done
9. **Quotation revision chain** - `parentQuotId` has no circular-reference check
<!-- 10. **Cost points hardcoded** - `costPoint1` through `costPoint20` as fixed columns; can't add more dynamically -->

### Code Quality
11. **No tests** - no `tests/` directory exists
12. **No structured error responses** - raw HTTPException with string detail; no error codes or request IDs
13. **No logging** - no file/structured logging configured
14. **Inconsistent column naming** - mix of camelCase (`companyId`), lowercase (`diaid`), and UPPERCASE (`GSTN`, `PAN`)
15. **Email service status unclear** - `core/email.py` and `api/v1/email.py` exist but may be incomplete
16. **No down() in migrations** - rollback support is unclear

### Production Readiness
17. **No audit trail queries** - `createdby`/`lastupdateby` fields exist but aren't exposed via API
18. **No cache layer** - every request hits DB
19. **No background task queue** - email sending blocks the request
20. **Soft-delete accumulation** - no cleanup strategy for `isActive=False` records
