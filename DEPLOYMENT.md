# SNM Portal — Deployment Guide

## Architecture Overview

```
Browser (HTTPS)
    |
    v
IIS (app.srmb.co.in:443)
    |
    +-- /snmportal/*.js, *.css, *.html  -->  Static files (Angular SPA)
    |
    +-- /snmportal/api/*  -->  Reverse Proxy --> http://localhost:8000/api/*  (FastAPI)
```

## Server Structure

```
C:\inetpub\wwwroot\snmportal\
├── web.config              <-- IIS rewrite rules (API proxy + SPA fallback)
├── index.html              <-- Angular entry point
├── main-XXXX.js            <-- Angular main bundle (hashed)
├── styles-XXXX.css         <-- Angular styles (hashed)
├── chunk-*.js              <-- Lazy-loaded Angular modules (hashed)
├── favicon.ico
├── assests/                <-- Background images (note: legacy spelling)
│   ├── bg.png              <-- Light theme background
│   ├── bg1.png             <-- Dark theme background
│   └── ...
└── backend\                <-- FastAPI application (runs on port 8000)
    ├── app\
    ├── alembic\
    ├── requirements.txt
    ├── .env
    └── ...
```

## Prerequisites (Windows Server / IIS)

### IIS Features
- IIS with **URL Rewrite** module installed
- **Application Request Routing (ARR)** installed
- **ARR Proxy enabled**: IIS Manager > Server level > Application Request Routing Cache > Server Proxy Settings > **Enable proxy** = checked

### Backend Requirements
- Python 3.10+
- ODBC Driver 18 for SQL Server
- SQL Server instance with `SNMPortal` database

---

## Step-by-Step Deployment

### 1. Backend Setup

```cmd
cd C:\inetpub\wwwroot\snmportal\backend

:: Install dependencies
pip install -r requirements.txt

:: Configure .env (copy from .env.example and fill values)
:: Key settings:
::   DB_CONNECTION_STRING=mssql+pyodbc://user:pass@host/SNMPortal?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=no
::   JWT_SECRET_KEY=<strong-random-key>
::   CORS_ORIGINS=http://localhost:4200,https://app.srmb.co.in
::   FILE_STORAGE_MODE=local  (or azure_blob)

:: Run migrations
alembic upgrade head

:: Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend Build (on dev machine)

**IMPORTANT:** Use PowerShell or Command Prompt. If using Git Bash, prefix with `MSYS_NO_PATHCONV=1` to prevent path mangling.

```powershell
cd C:\Projects Code Bases\SNM-portal\frontend

# Clean previous build
Remove-Item -Recurse -Force dist, .angular -ErrorAction SilentlyContinue

# Production build
npx ng build --configuration production --base-href /snmportal/
```

**Using Git Bash:**
```bash
cd "c:/Projects Code Bases/SNM-portal/frontend"
rm -rf dist .angular
MSYS_NO_PATHCONV=1 npx ng build --configuration production --base-href /snmportal/
```

**Verify build output:**
```bash
# Check base href is correct (should be /snmportal/, NOT C:/Program Files/...)
grep -o 'base href="[^"]*"' dist/frontend/browser/index.html

# Check API URL is relative
grep -o 'apiUrl:"[^"]*"' dist/frontend/browser/chunk-*.js
# Should show: apiUrl:"/snmportal/api/v1"
```

### 3. Deploy Frontend to Server

```cmd
:: On the server — clear old frontend files (keep backend folder and web.config)
cd C:\inetpub\wwwroot\snmportal
del /q *.js *.css *.html *.ico *.map 2>nul
rmdir /s /q assests 2>nul

:: Copy new build output
xcopy "\\dev-machine\path\dist\frontend\browser\*" "." /s /e /y
```

### 4. Deploy web.config

Place this at `C:\inetpub\wwwroot\snmportal\web.config`:

```xml
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="FastAPI Proxy" stopProcessing="true">
          <match url="^api/(.*)" />
          <action type="Rewrite" url="http://localhost:8000/api/{R:1}" />
        </rule>
        <rule name="Angular Routes" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="index.html" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

**Rule 1 (FastAPI Proxy):** Routes `/snmportal/api/*` to `http://localhost:8000/api/*`
**Rule 2 (SPA Fallback):** All non-file URLs serve `index.html` for Angular client-side routing

### 5. Verify Deployment

1. Open `https://app.srmb.co.in/snmportal/` in **incognito** browser
2. DevTools > Network tab: check that `main-XXXX.js` matches the build hash
3. Login and navigate to Companies, Users, Masters, Enquiries, Quotations
4. Console should have **no mixed content errors**
5. All API calls should go to `https://app.srmb.co.in/snmportal/api/v1/...`

---

## Environment Configuration

### Frontend Environments

| File | Purpose | apiUrl |
|------|---------|--------|
| `environment.ts` | Development (`ng serve`) | `http://localhost:8000/api/v1` |
| `environment.prod.ts` | Production (`ng build`) | `/snmportal/api/v1` (relative) |

The `fileReplacements` in `angular.json` swaps `environment.ts` with `environment.prod.ts` during production builds.

### Backend Key Settings

| Setting | Dev | Prod |
|---------|-----|------|
| `redirect_slashes` | `False` | `False` |
| `CORS_ORIGINS` | `http://localhost:4200` | `http://localhost:4200,https://app.srmb.co.in` |
| `FILE_STORAGE_MODE` | `local` | `local` or `azure_blob` |
| `DEBUG` | `true` | `false` |

### Backend Route Convention
All collection root routes use `""` (empty string), not `"/"`. This is required because `redirect_slashes=False` is set to prevent IIS reverse proxy mixed-content issues.

```python
# Correct
@router.get("")        # matches /api/v1/companies
@router.post("")       # matches /api/v1/companies

# Wrong — will 404 with redirect_slashes=False
@router.get("/")       # only matches /api/v1/companies/
```

---

## IIS Settings Reference

### URL Rewrite Inbound Rule — FastAPI Proxy

| Setting | Value |
|---------|-------|
| Name | FastAPI Proxy |
| Match URL | Matches the Pattern |
| Using | Regular Expressions |
| Pattern | `^api/(.*)` |
| Ignore case | Yes |
| Action type | Rewrite |
| Rewrite URL | `http://localhost:8000/api/{R:1}` |
| Append query string | Yes |
| Stop processing | Yes |

### URL Rewrite Inbound Rule — Angular SPA

| Setting | Value |
|---------|-------|
| Name | Angular Routes |
| Match URL | `.*` |
| Conditions | Match All |
| Condition 1 | `{REQUEST_FILENAME}` is NOT a File |
| Condition 2 | `{REQUEST_FILENAME}` is NOT a Directory |
| Action type | Rewrite |
| Rewrite URL | `index.html` |
| Stop processing | Yes |

### Application Request Routing (Server Level)

| Setting | Value |
|---------|-------|
| Enable proxy | Yes |
| HTTP version | Pass through |
| Keep alive | Yes |
| Time-out | 120 seconds |
| Reverse rewrite host in response headers | Yes |

---

## Troubleshooting

### Mixed Content Errors (`http://` instead of `https://`)
**Cause:** FastAPI `redirect_slashes` sends `307 Redirect` with `http://` Location header through the reverse proxy.
**Fix:** Ensure `redirect_slashes=False` in `main.py` AND all collection routes use `""` not `"/"`.

### `file:///C:/Program Files/Git/snmportal/` in base href
**Cause:** Git Bash MSYS path conversion mangled the `--base-href` flag.
**Fix:** Use `MSYS_NO_PATHCONV=1` prefix when building in Git Bash, or use PowerShell/cmd.

### 404 on page refresh (e.g., `/snmportal/customers`)
**Cause:** Missing SPA fallback rule in web.config.
**Fix:** Add the "Angular Routes" rewrite rule that serves `index.html` for non-file URLs.

### Chunk load errors (`Failed to fetch dynamically imported module`)
**Cause:** Old build files on server mixed with new `index.html`.
**Fix:** Always delete ALL old frontend files before deploying new build.

### Background images not loading
**Cause:** CSS uses absolute paths like `/snmportal/assests/bg.png`.
**Fix:** The `styles.scss` must use `/snmportal/assests/bg.png` (matching the base-href). In dev, `ng serve` serves from `/` so the images load from the `public/` folder.

### Session timeout / 401 errors
**Cause:** JWT access token expires after 30 minutes.
**Fix:** User must re-login. Auto-refresh is not yet implemented.

---

## Pagination & Performance Overhaul (Production Scale)

This release upgrades the app to handle **5,000–50,000 rows per entity** without
degradation. Rolled out in 6 additive phases — no breaking changes.

### What Changed

| Phase | Change | Files |
|---|---|---|
| P1 | 30+ filtered DB indexes on hot paths | `alembic/versions/n8o9p0q1r2s3_perf_indexes_phase1.py` |
| P2 | In-process TTL cache (visibility, location, role perms, masters) | `app/core/cache.py`, `app/core/cache_keys.py`, `app/services/cache_invalidation.py` |
| P3 | Cursor pagination + `/search` endpoints for customer/user/enquiry/quotation | `app/core/cursor_pagination.py`, endpoints added to `api/v1/customers.py`, `users.py`, `enquiries.py`, `quotations.py` |
| P4 | Reusable `<app-server-search-select>` component with virtual scroll + infinite scroll + debounce | `shared/components/server-search-select/` |
| P5 | 7 dropdowns migrated to server-side search | enquiry-form, quotation-form (customer + enquiry), handover-dialog, user-dialog (reportTo), enquiry-list + quotation-list filters |
| P6 | `MAX_PAGE_SIZE` 100→500, paginator options up to 500, slow-query middleware, frontend ref-data cache | `app/core/pagination.py`, `app/core/slow_query_middleware.py`, `app/main.py`, `core/services/reference-data.service.ts`, list components |

### Deploy Steps

1. **Install new Python deps** (adds `cachetools`):
   ```bash
   cd C:\inetpub\wwwroot\snmportal\backend
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Run the index migration** (takes ~1–5 min on 50k-row tables):
   ```bash
   alembic upgrade head
   ```
   Migration `n8o9p0q1r2s3_perf_indexes_phase1` creates 30+ filtered indexes.
   All indexes use `WHERE isActive = 1` so soft-deleted rows don't bloat them.

3. **Set slow-query threshold** (optional, defaults to 2000ms):
   Add to `backend\.env`:
   ```
   SLOW_QUERY_THRESHOLD_MS=2000
   ```
   Endpoints slower than this log a WARNING to the backend log.

4. **Restart FastAPI** (the cache is process-memory; restart clears it — fine):
   ```powershell
   Restart-WebAppPool -Name "SNMPortalBackend"
   # or stop/start the uvicorn service
   ```

5. **Deploy frontend** as usual (`ng build --configuration production`, copy `dist/frontend/*` to IIS wwwroot).

### What's New for Users

- **Fast dropdowns**: Customer/User/Enquiry pickers now search-as-you-type with infinite scroll; no 100-row cap.
- **Larger list pages**: Customer, Enquiry, Quotation, Communication Log paginators now offer 250 and 500 rows/page.
- **Response-time header**: Every API response includes `X-Response-Time-Ms` for DevTools monitoring.

### Cache Invalidation

Automatic — all write endpoints call the right hook. Admins do NOT need to manually flush cache after data changes.

- User role/reportTo change → clears visibility + location company-wide
- User location change → clears location cache company-wide
- Role flag change → clears role_settings + permissions + visibility/location
- RoleMenuMap change → clears role_perms + menu_tree
- Master data change → clears that entity's cache per company

### Monitoring

After deploy, check the backend log for `slow_query` WARNING entries. If a specific endpoint repeatedly appears:
1. Confirm indexes from P1 are created (run: `SELECT name FROM sys.indexes WHERE name LIKE 'IX_%'`)
2. Check if the endpoint was missed in cache migration
3. Raise threshold temporarily (`SLOW_QUERY_THRESHOLD_MS=5000`) if false positives are noisy

### Rollback

All changes are additive:
- Indexes can be dropped via `alembic downgrade -1` (migration downgrade is defined)
- Cache is in-process, zero external state to roll back
- Old `/customers`, `/enquiries`, etc. list endpoints work unchanged
- Frontend: the old dropdown pattern still works on any component that wasn't migrated

If a production issue forces rollback of P3/P4/P5, simply redeploy the previous frontend; the new `/search` endpoints will keep working alongside the old `/list` endpoints and cause no conflict.
