# SNMZIp v1.0 — Severity-Wise Issue Report

> Audit Date: 2026-04-26

---

## Summary

| Severity | Count |
|---|---|
| Critical | 6 |
| High | 11 |
| Medium | 14 |
| Low | 8 |
| **Total** | **44** |

---

## Critical (6)

| # | Issue | File / Location |
|---|---|---|
| C1 | **Plaintext SMTP passwords in DB** — `MailPassword` stored and used unencrypted | `backend/app/models/company.py:26`, `backend/app/services/email_service.py:53` |
| C2 | **XSS via `bypassSecurityTrustHtml()`** — quotation format templates bypass Angular sanitizer | `frontend/src/app/features/quotations/quotation-print/quotation-print.component.ts:698-702` |
| C3 | **Missing role-based auth on most API endpoints** — `/users`, `/roles`, `/masters/*` lack `require_permission()` | `backend/app/api/v1/*.py` |
| C4 | **JWT tokens stored in `localStorage`** — vulnerable to XSS theft; should use HttpOnly cookies | `frontend/src/app/core/auth/token.service.ts` |
| C5 | **No CSRF protection** — no CSRF token on POST/PUT/DELETE endpoints | All mutation endpoints |
| C6 | **Email endpoint skips visibility checks** — any user can send emails for any quotation | `backend/app/api/v1/email.py:26-79` |

### C1 — Plaintext SMTP Passwords in DB
**Impact:** Any database breach exposes plaintext credentials for company email accounts. Attacker can send emails impersonating the company or pivot to email infrastructure.
**Fix:** Encrypt using `cryptography.Fernet` or store in a secrets vault (Azure Key Vault, AWS Secrets Manager).

### C2 — XSS via `bypassSecurityTrustHtml()`
**Impact:** Full XSS — attacker with template edit access can steal tokens, impersonate users, exfiltrate data.
```typescript
// Vulnerable pattern in quotation-print.component.ts
this.renderedHeader = this.sanitizer.bypassSecurityTrustHtml(this.replacePlaceholders(fmt.qHeader));
```
**Fix:** Remove `bypassSecurityTrustHtml()`. Use safe DOM construction or a server-side template renderer.

### C3 — Missing Role-Based Auth on API Endpoints
**Impact:** Privilege escalation — users can access resources they shouldn't (e.g., list all users without `Users:CanRead`).
**Fix:** Add `dependencies=[Depends(require_permission("MenuName", "CanRead"))]` to every router.

### C4 — JWT Tokens in `localStorage`
**Impact:** Any XSS vulnerability fully compromises the session. Attacker can persist access even after victim closes browser.
**Fix:** Switch to HttpOnly, Secure, SameSite=Strict cookies for token storage.

### C5 — No CSRF Protection
**Impact:** Attacker can trick logged-in users into performing state-changing actions via forged requests.
**Fix:** Implement CSRF token validation or use SameSite cookie policy alongside C4 fix.

### C6 — Email Endpoint Skips Visibility Checks
**Impact:** Information disclosure — users can enumerate quotations they don't own; spam/phishing via company SMTP.
**Fix:** Apply the same hierarchy + location filters used in `/quotations` endpoints before sending.

---

## High (11)

| # | Issue | File / Location |
|---|---|---|
| H1 | **Internal error details leaked in responses** — `str(e)` returned to client | `backend/app/api/v1/email.py:78` |
| H2 | **No rate limiting beyond login** — all other endpoints unprotected | `backend/app/core/rate_limit.py` |
| H3 | **No file upload size limit for `general` category** — DoS via large files | `backend/app/api/v1/assets.py:40-43` |
| H4 | **Email sending is synchronous** — slow SMTP blocks the request thread | `backend/app/api/v1/email.py:69-78` |
| H5 | **No circular reference guard on quotation revision chain** — `parentQuotId` can loop | `backend/app/models/quotation.py` |
| H6 | **Unvalidated HTML in email body** — `data.htmlBody` sent as-is without sanitization | `backend/app/api/v1/email.py:57-67` |
| H7 | **Soft-delete bloat with no cleanup/archive policy** — no retention strategy | All models (`isActive` flag) |
| H8 | **SMTP config unprotected in Company table** — readable by anyone with DB access | `backend/app/models/company.py:25-28` |
| H9 | **Mutual reporting loop possible** — `reportTo` self-FK with no cycle detection | `backend/app/models/user.py` |
| H10 | **No password reset / change-password endpoint** — profile dialog returns 404 | `backend/app/api/v1/auth.py` |
| H11 | **Zero test coverage** — no unit, integration, or E2E tests across codebase | Entire codebase |

### H1 — Internal Error Details Leaked
```python
raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
```
**Fix:** Log the full exception server-side; return a generic message to the client.

### H2 — No Rate Limiting Beyond Login
**Fix:** Apply `slowapi` or a custom rate limiter to search, list, and upload endpoints.

### H3 — No File Size Limit for General Uploads
```python
CATEGORY_MAX_SIZE_BYTES = {
    "po_document": 20 * 1024 * 1024,  # Only po_document limited
}
max_size = CATEGORY_MAX_SIZE_BYTES.get(cat)  # Returns None for 'general' → no limit
```
**Fix:** Add a default fallback limit (e.g., 10 MB) for all categories.

### H4 — Synchronous Email Sending
**Fix:** Use `BackgroundTasks` (FastAPI) or a task queue (Celery/ARQ) to send emails asynchronously.

### H5 — Circular Quotation Revision Chain
**Fix:** Before creating a revision, walk the `parentQuotId` chain and reject if the new quotId already appears.

### H6 — Unvalidated HTML in Email Body
**Fix:** Sanitize `data.htmlBody` with `bleach` (Python) before sending.

### H7 — Soft-Delete Bloat
**Fix:** Define a data retention policy; add a scheduled job to hard-delete or archive records older than N months.

### H8 — SMTP Config in Company Table
**Fix:** Move SMTP credentials to a secrets vault or an encrypted column; restrict DB-level read access.

### H9 — Mutual Reporting Loop
**Fix:** On user save, run a cycle-detection check (DFS/BFS on `reportTo` chain) and reject if a loop is detected.

### H10 — No Change Password Endpoint
**Fix:** Implement `POST /auth/change-password` accepting `{currentPassword, newPassword}` with bcrypt verification.

### H11 — Zero Test Coverage
**Fix:** Start with critical path integration tests: login, quotation creation, permission enforcement.

---

## Medium (14)

| # | Issue | File / Location |
|---|---|---|
| M1 | **Hardcoded company info in quotation print** — GSTIN, address, phone are placeholder values | `quotation-print.component.ts:~91` |
| M2 | **No global error handler on frontend** — unhandled errors crash silently | `frontend/src/app/app.config.ts` |
| M3 | **No audit log for admin actions** — role/permission changes leave no trail | `backend/app/api/v1/roles.py`, `users.py` |
| M4 | **Numeric inputs have no range validation** — negative quantities/rates accepted | `backend/app/schemas/*.py` |
| M5 | **Search parameter has no length limit** — potential resource exhaustion | `backend/app/api/v1/*.py` (search endpoints) |
| M6 | **Status values are plain strings, not enums** — typo-prone throughout | `backend/app/models/quotation.py`, `enquiry.py` |
| M7 | **No structured/centralized logging on backend** | `backend/app/main.py` |
| M8 | **No API versioning strategy** — breaking changes will affect all clients | `backend/app/api/v1/router.py` |
| M9 | **Circular user reporting not detected** — `reportTo` cycle breaks hierarchy BFS | `backend/app/services/access_service.py` |
| M10 | **Phone/email fields accept any string** — no format validation in Pydantic schemas | `backend/app/schemas/user.py`, `customer.py` |
| M11 | **`userDesignation` not used in access control** — creates false security assumptions | `backend/app/models/user.py` |
| M12 | **Inconsistent DB column naming** — `companyId` (camelCase) vs `enqid`, `enqdtlid` (lowercase) | All models |
| M13 | **`sa` SQL Server account in `.env.example`** — copy-paste risk into production | `backend/.env.example:2` |
| M14 | **No SMTP connection timeout** — hangs indefinitely if mail server unresponsive | `backend/app/services/email_service.py` |

---

## Low (8)

| # | Issue | File / Location |
|---|---|---|
| L1 | **Asset path typo** — `/assests/` instead of `/assets/` in styles | `frontend/src/styles.scss` |
| L2 | **No 404 page** — wildcard route redirects to `/dashboard` | `frontend/src/app/app.routes.ts:140` |
| L3 | **Mixed Angular template syntax** — `*ngIf`/`*ngFor` and `@if`/`@for` coexist | `frontend/src/app/features/` |
| L4 | **No virtual scrolling** — all table rows rendered in DOM for large datasets | All list components |
| L5 | **Master data re-fetched on every navigation** — no client-side caching | `frontend/src/app/core/services/api.service.ts` |
| L6 | **Build budget warning** — `quotation-print.component.ts` exceeds style budget by 67 bytes | `frontend/angular.json` |
| L7 | **Status enums not strongly typed** — string literals used throughout | `backend/app/models/`, `frontend/src/app/features/` |
| L8 | **No APM / performance monitoring configured** | `backend/app/main.py`, `frontend/` |

---



## Immediate Action Items

1. Encrypt SMTP passwords — C1
2. Remove `bypassSecurityTrustHtml()` from quotation print — C2
3. Enforce `require_permission()` on all API endpoints — C3
4. Move tokens from `localStorage` to HttpOnly cookies — C4
5. Add quotation ownership check in email endpoint — C6
6. Return generic error messages to client; log details server-side — H1
7. Add file upload size limit for all categories — H3
8. Implement change-password endpoint — H10
9. Add global error handler in `app.config.ts` — M2
10. Add SMTP connection timeout — M14
