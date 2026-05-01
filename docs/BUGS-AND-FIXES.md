# SNM Portal - Bugs & Fixes Log

## Resolved Issues

### 1. Menu URLs mismatch (singular vs plural)
- **Problem:** Seeded menu URLs used singular slugs (`/masters/item-grade`) but Angular routes used plural (`/masters/item-grades`). Sidebar links led to 404s.
- **Fix:** Migration `f3a1b2c4d5e6` updates all menu URLs from singular to plural form.

### 2. Missing location/dia tables
- **Problem:** Frontend had routes and components for Country, State, District, and Dia Master, but no corresponding database tables existed.
- **Fix:** Migration `a1b2c3d4e5f6` creates the 4 tables. Migration `b2c3d4e5f6a7` adds menu entries and permissions.

### 3. Role-Menu Mapping duplicate sidebar entry
- **Problem:** "Role-Menu Mapping" appeared as a separate submenu under Administration, but it's accessed from within Role Management (via the mapping icon on each role row). Redundant sidebar entry.
- **Fix:** Migration `c3d4e5f6a7b8` soft-deletes the menu entry.

### 4. Angular component style budget exceeded
- **Problem:** `org-tree.component.scss` and `quotation-print.component.scss` exceeded the 4kB `anyComponentStyle` budget warning threshold, causing build warnings.
- **Fix:** Bumped budget in `angular.json` from `4kB warning / 8kB error` to `6kB warning / 10kB error`.

### 5. dagre CommonJS module warning
- **Problem:** `dagre` is a CommonJS package. Angular build warned: "Module 'dagre' used by org-tree.component.ts is not an ECMAScript module".
- **Fix:** Added `"allowedCommonJsDependencies": ["dagre"]` to `angular.json` build options.

### 6. Organization Tree — root vs unassigned user distinction
- **Problem:** Both "root" nodes (top of hierarchy) and "unassigned" users had `reportTo = NULL`, making them indistinguishable.
- **Fix:** Adopted self-reference convention: `reportTo = userId` (self) marks a root node. `reportTo = NULL` means unassigned. No DB schema changes needed.

### 7. Organization Tree — circular reference risk
- **Problem:** Assigning user A to report to user B when B already reports to A (directly or transitively) would create an infinite loop.
- **Fix:** Backend `_creates_cycle()` function in `org_tree.py` walks up the reporting chain from the proposed parent to detect cycles before allowing assignment.

### 8. Org-tree based visibility for Enquiries & Quotations
- **Problem:** All users within a company could see all enquiries and quotations, regardless of org hierarchy. No row-level access control based on reporting structure.
- **Fix:** Added `visibility_service.py` that walks the org tree (via `reportTo`) to compute visible user IDs (self + all transitive subordinates). Enquiry and Quotation list/get/update/delete/revise/approve endpoints now filter by `createdby ∈ visible_users`. SuperAdmins bypass the filter and see everything.

---

## Known Considerations

### Org Tree — Cascade unassign on remove
- **Current behavior:** When removing a user from the org tree (frontend), their direct children are also set to unassigned in local state. The backend `PUT /assign` endpoint only updates one user at a time.
- **Recommendation:** For production, use the `PUT /bulk-assign` endpoint to cascade unassign children, or add a dedicated cascade endpoint.

### Multi-company user management
- A single user can manage multiple companies via `UserRoleMap` — each mapping assigns a different role per company.
- Login returns all accessible companies → user selects one → JWT is issued with `{user_id, company_id, role_id}`.
- Company switching (`POST /auth/switch-company`) re-issues the JWT without re-login.
- All API queries are scoped to the active `companyId` from the JWT.

### Email configuration is optional
- SMTP fields on Company are all nullable. If not configured, email features should be hidden/disabled in the UI for that company.

### Password column size
- `userPassword` is `String(255)` to accommodate bcrypt hashes (60 chars). Original schema had smaller size.
