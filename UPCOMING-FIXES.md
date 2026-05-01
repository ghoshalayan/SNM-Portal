# SNM Portal — Upcoming Fixes

Full-stack bug audit consolidated by severity. Each item links to the offending file/line and includes a one-line fix hint. Work top-down.

**Audit date:** 2026-04-24
**Last updated:** 2026-04-26 — 27 of 52 items fixed in code; secret rotations (#1, #2, #23) and one env-value flip (#4) remain user-owned.
**Scope:** FastAPI backend + Angular 21 frontend + IIS/infra config

**Legend:** `[x]` = done · `[ ]` = open · `🔒` = requires user action (secret rotation / env edit) — code-side ready.

---

## CRITICAL (fix first)

### Security & Multi-tenant Isolation

- [ ] 🔒 **1. Azure Storage account key committed in plain text** — [backend/.env:17](backend/.env#L17)
  Full R/W/delete exposure to `srmbsaci` / `srmb-resources`. **Rotate key in Azure portal**, add `.gitignore`, move to Key Vault / env var injection at IIS level.

- [ ] 🔒 **2. SQL Server credentials committed in plain text** — [backend/.env:4](backend/.env#L4)
  Same exposure. Rotate password, move to env-only config.

- [x] **3. CORS hardcoded to `*`** — [backend/app/main.py:20](backend/app/main.py#L20)
  Replaced `origins = ["*"]` with `settings.cors_origins_list`.

- [x] **4. `DEBUG=true` in committed prod .env** — [backend/.env:27](backend/.env#L27)
  Code: `/docs`, `/redoc`, `/openapi.json` are now gated behind `settings.DEBUG`. **🔒 You still need to flip the env value to `DEBUG=false` in production.**

- [x] **5. User/Role queries in auth miss `companyId` filter** — [backend/app/api/v1/auth.py:31-32](backend/app/api/v1/auth.py#L31-L32), [:146](backend/app/api/v1/auth.py#L146)
  Defence-in-depth scope on Role + User fetch in `_build_token_response`.

- [x] **6. CustomerSite fetch missing `companyId` in enquiry upload** — [backend/app/api/v1/enquiries.py:236](backend/app/api/v1/enquiries.py#L236)
  Now filters by `companyId + isActive`, returns 404 on mismatch.

- [x] **7. `QuotSummary` fetch missing `companyId` in asset endpoints** — [backend/app/api/v1/assets.py:196, 288, 336](backend/app/api/v1/assets.py#L196)
  All three lookups (upload / download-log / delete-log) tenant-scoped.

### Business-logic correctness

- [x] **8. Quotation number generation race** — [backend/app/api/v1/quotations.py:406-410](backend/app/api/v1/quotations.py#L406-L410)
  Migration `u5v6w7x8y9z0_unique_quot_enq_numbers` adds filtered `UNIQUE(companyId, quotNo)`. New `services/number_allocator.py` retries on IntegrityError up to 10× for auto-generated numbers; user-supplied numbers fail fast with 409.

- [x] **9. Enquiry number generation race** — [backend/app/api/v1/enquiries.py:265-269](backend/app/api/v1/enquiries.py#L265-L269)
  Same migration adds `UNIQUE(companyId, enqNo)`; same allocator helper used.

- [x] **10. Quotation revision number corruption** — [backend/app/services/quotation_service.py:52-53](backend/app/services/quotation_service.py#L52-L53)
  Replaced brittle `split("-R")[0]` with anchored regex `-R\d+$`.

### Frontend data integrity

- [x] **11. Quotation form patchValue ordering bug** — [quotation-form.component.ts:784-815](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L784-L815)
  `saveQuotation()` now uses `getRawValue()` so disabled controls survive the round-trip; `invalid` check skipped when form fully disabled.

- [x] **12. Customer lock + enquiry change race** — [quotation-form.component.ts:831-839](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L831-L839)
  `onEnquiryChange` snapshots disabled state, enables silently, patches, re-disables.

---

## HIGH

### Backend

- [x] **13. Approve endpoint accepts any status** — [quotations.py:648-670](backend/app/api/v1/quotations.py#L648-L670)
  Now rejects anything but `Draft` (400 with pointer to `/revert-reject` for Rejected).

- [x] **14. Revert-reject leaves approval audit trail blank** — [quotations.py:739-757](backend/app/api/v1/quotations.py#L739-L757)
  Captures prior `approvedby/on` in activity log; fills in reverter as fallback when trail is blank.

- [x] **15. Handover does not re-check enquiry status lock** — [enquiries.py:293-295](backend/app/api/v1/enquiries.py#L293-L295)
  Enquiry handover blocks `Quotation Prepared`, `Reject`, `Expired`.

- [x] **16. Handover clears `approvedby/on` without archiving** — [quotations.py:536-541](backend/app/api/v1/quotations.py#L536-L541)
  Logs `"Approval cleared by handover"` activity row with prior approver before clearing; ownership-handover log includes from→to + reopen note.

- [x] **17. Cursor pagination `last_id` extraction broken for Row objects** — [backend/app/core/cursor_pagination.py:119](backend/app/core/cursor_pagination.py#L119)
  Uses `getattr(last, id_col.key)` unconditionally with mapping-shape fallback.

- [x] **18. Role query lacks `companyId` scope** — [auth.py:32](backend/app/api/v1/auth.py#L32)
  Covered by #5 in CRITICAL batch.

- [x] **19. User creation role mappings not company-scoped** — [users.py:322](backend/app/api/v1/users.py#L322)
  `_validate_role_mappings` now takes a `target_company_id` and enforces non-SuperAdmin callers keep mappings scoped to it.

- [x] **20. Quotation revision copy includes stale soft-deleted rows** — [quotation_service.py:86-113](backend/app/services/quotation_service.py#L86-L113)
  Verified — already filters `isActive == True` on `QuotDetails` and `QuotTermsNConditions` copies. No change needed.

- [x] **21. Sort column injection via `getattr(QuotSummary, pagination.sort_by, None)`** — [quotations.py:157-161](backend/app/api/v1/quotations.py#L157-L161)
  New `resolve_sort_column()` helper in `core/pagination.py` with per-endpoint whitelists across quotations / enquiries / customers / users. Bad `sortBy` → 400 with allowed list.

### Infra

- [x] **22. No `.gitignore` in repo root**
  Created. Covers `backend/.env`, venv, node_modules, .angular cache, logs, IDE caches, test reports, build artefacts.

- [ ] 🔒 **23. `LOCAL_STORAGE_PATH=azure_blob`** — [backend/.env:14](backend/.env#L14)
  Set to `uploads` or remove when `FILE_STORAGE_MODE=azure_blob`. Env-value tweak — your call.

- [x] **24. Seed migration downgrade does `DELETE FROM` with no WHERE** — [e88c297e3e9d_seed_superadmin_test_user_company_menus_.py:213-221](backend/alembic/versions/e88c297e3e9d_seed_superadmin_test_user_company_menus_.py#L213-L221)
  Replaced with `RuntimeError` explaining why downgrade is disabled (the old version ran unscoped DELETE across 6 tables).

- [x] **25. RBAC seed migration missing/partial downgrade** — [g1h2i3j4k5l6_seed_rbac_role_templates.py](backend/alembic/versions/g1h2i3j4k5l6_seed_rbac_role_templates.py)
  Verified — already had safe `pass` with reasoning comment.

### Frontend

- [x] **26. Auth interceptor logs out on 401 without refresh** — [auth.interceptor.ts:39-46](frontend/src/app/core/interceptors/auth.interceptor.ts#L39-L46)
  Full interceptor rewrite — concurrent 401s share a single `/auth/refresh` call via `BehaviorSubject`; exempt list (login/refresh/select-company/switch-company) bypasses the retry loop; logout only when refresh itself fails.

- [x] **27. Subscription leaks in `loadDropdowns`** — [quotation-form.component.ts:744-756](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L744-L756)
  All three subscriptions piped through `takeUntilDestroyed(this.destroyRef)`.

- [x] **28. Subscription leaks in customer form** — [customer-form.component.ts:281-285](frontend/src/app/features/customers/customer-form/customer-form.component.ts#L281-L285)
  `loadClassifications` got the same treatment.

- [x] **29. Disabled controls + `required` validators inconsistency** — quotation-form Matured path
  Covered by #11 — `getRawValue()` keeps disabled controls in the payload; `invalid` check skipped when fully disabled.

- [x] **30. Wildcard route redirects to `login`** — [app.routes.ts:116](frontend/src/app/app.routes.ts#L116)
  Wildcard now redirects to `dashboard`; auth-less users still bounce to `/login` via interceptor.

---

## MEDIUM

### Backend

- [ ] **31. Location masters return unpaginated `.all()`** — [masters.py:876-929](backend/app/api/v1/masters.py#L876-L929)
  Countries/states/districts — paginate via cursor.

- [ ] **32. Customer sub-resource endpoints don't verify parent customer ownership** — [customers.py:248-353](backend/app/api/v1/customers.py#L248-L353)
  Fetch parent customer with company filter before accepting contact/site writes.

- [ ] **33. Approve skips completeness validation** — [quotations.py:648-666](backend/app/api/v1/quotations.py#L648-L666)
  Require >=1 detail line, delivery term, site before approve.

- [ ] **34. Enquiry→Quotation conversion does not copy enquiry details** — [quotations.py:423-431](backend/app/api/v1/quotations.py#L423-L431)
  Auto-copy enquiry line items with user-override capability.

- [ ] **35. `create_new_costing_version` silently creates empty version when `max_version==0`** — [costing_service.py:31-50](backend/app/services/costing_service.py#L31-L50)
  Raise if no prior version to copy from.

- [ ] **36. TnC master FK lookups don't filter `isActive`** — [quotations.py:207-214](backend/app/api/v1/quotations.py#L207-L214)
  Add `TermsNConditionMaster.isActive == True`.

### Frontend

- [ ] **37. Dialog `afterClosed()` subscriptions never unsubscribed** — [quotation-form.component.ts:915, 1060](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L915)
  Chain `takeUntilDestroyed()` or use `firstValueFrom`.

- [ ] **38. Customer list `searchSubject` never unsubscribed** — [customer-list.component.ts:280-282](frontend/src/app/features/customers/customer-list/customer-list.component.ts#L280-L282)
  Same.

- [ ] **39. `viabilityStatus` / `customerLocked` not reset on edit→new navigation** — [quotation-form.component.ts:659, 669](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L659)
  Initialize both in `ngOnInit` when `!isEditMode`.

- [ ] **40. `activeTab` hardcoded to 1 after save** — [quotation-form.component.ts:888](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L888)
  Only change tab on new→edit transition.

- [ ] **41. PO dirty check accepts null date** — [quotation-form.component.ts:1006-1010](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts#L1006-L1010)
  Validate `poDate?.value` is a real Date.

- [ ] **42. No cache on reference-data master calls**
  Add `shareReplay(1)` cache in a ReferenceDataService for read-only masters (delivery terms, modes, classifications).

### Infra

- [ ] **43. No security headers** — [backend/app/main.py](backend/app/main.py) + `web.config`
  Add middleware for `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, basic CSP.

- [ ] **44. `/local-files` static mount serves arbitrary content-types** — [main.py:38-41](backend/app/main.py#L38-L41)
  Validate MIME on upload; force `Content-Disposition: attachment` on download.

- [ ] **45. Backfill data migration is non-idempotent** — [k5l6m7n8o9p0_backfill_statuses.py:48-50](backend/alembic/versions/k5l6m7n8o9p0_backfill_statuses.py#L48-L50)
  Guard with "already backfilled" check or document as one-shot.

---

## LOW

- [ ] **46. Timing-attack-friendly login path** — [auth.py:19](backend/app/api/v1/auth.py#L19)
  Always run password hash compare even when user is missing.

- [ ] **47. UTC vs IST mixing in token expiry** — [core/security.py:25](backend/app/core/security.py#L25)
  Use `now_ist()` consistently.

- [ ] **48. Dynamic router generation in masters harder to audit** — [masters.py](backend/app/api/v1/masters.py)
  Move to explicit router registration or a typed registry.

- [ ] **49. Quotation print silently uses `ownerName: None`** — [quotations.py:248-258](backend/app/api/v1/quotations.py#L248-L258)
  Fall back to a sentinel or raise.

- [ ] **50. SAS token default expiry 1h** — [azure_blob_service.py:63-76](backend/app/services/azure_blob_service.py#L63-L76)
  Increase to 24h or make per-endpoint configurable.

- [ ] **51. `revisionNo = versionNo - 1` semantic mismatch** — [quotation_service.py:76](backend/app/services/quotation_service.py#L76)
  Pick one representation and drop the other.

- [ ] **52. IIS web.config lacks outbound Location/Set-Cookie rewrite** — [web.config](web.config)
  Add outbound rules so backend-issued redirects use the public host.

---

## Recommended order of attack

1. **Today (hours):** Items 1–4, 22 — rotate secrets, add `.gitignore`, purge `.env` from history, fix CORS, disable DEBUG.
2. **This week:** Items 5–7, 18, 32 — apply `companyId` filter to every unscoped query. Items 8–9 — add `UNIQUE(companyId, quotNo)` / `UNIQUE(companyId, enqNo)` constraints.
3. **Next sprint:** Items 11–12 (quotation form patchValue), 26 (token refresh end-to-end), 13–14 (state-machine guards on approve/mature/revert).
4. **Cleanup pass:** Subscription-leak sweep (27–28, 37–38) via `takeUntilDestroyed()`; paginate location masters (31); sort-column whitelist (21).

---

## Status (as of 2026-04-26)

| Severity | Total | Fixed in code | User-owned (env / secrets) | Open |
|---|---|---|---|---|
| CRITICAL | 12 | **10** | 2 (#1, #2) + #4 partial | 0 |
| HIGH     | 18 | **17** | 1 (#23) | 0 |
| MEDIUM   | 15 | 0 | 0 | 15 |
| LOW      | 7  | 0 | 0 | 7 |
| **Total** | **52** | **27** | **3** | **22** |

Open queue is the entire MEDIUM (31–45) and LOW (46–52) bands. CRITICAL + HIGH are code-clean; only secret rotations + one env-value flip need human action.
