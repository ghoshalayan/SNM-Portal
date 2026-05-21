# SNM Portal — Issue Tracker

> **Last updated: 2026-05-05**
> Original audit (2026-04-26) preserved at the bottom of this file.

---

## Status snapshot

| Severity | Original (2026-04-26) | Fixed since | Still open | New findings (open) |
|---|---:|---:|---:|---:|
| Critical | 6 | 1 fully + 2 partial | 3 | — |
| High | 11 | 1 partial | 10 | 6 |
| Medium | 14 | — | 14 | 2 |
| Low | 8 | — | 8 | — |
| Schema (new class) | — | — | — | 8 |
| **Total** | **44** | **2 + 3 partial** | **35** | **16** |

The "fixed" column includes only items closed end-to-end this session. Partials still appear in the open list with the specific remaining work called out.

---

## Resolved since 2026-04-26

### From the original audit

| ID | Issue | Status | Reference |
|---|---|---|---|
| C6 | Email endpoint skipped visibility checks | **FIXED** | Routed through `_get_quot_or_403`; contact lookup tenant-scoped; CR/LF stripped from subject. [`backend/app/api/v1/email.py`](backend/app/api/v1/email.py) |
| C2 | XSS via `bypassSecurityTrustHtml()` | **PARTIAL** | Placeholder values + line-items + T&C now HTML-escaped at the boundary. The template body itself still uses `bypassSecurityTrustHtml` (admin-authored rich HTML — DOMPurify allowlist is the remaining piece). [`quotation-print.component.ts`](frontend/src/app/features/quotations/quotation-print/quotation-print.component.ts) |
| C3 | Missing role-based auth on API endpoints | **PARTIAL** | Specific IDORs closed (see N1, N2, N3, N4 below). Broader endpoint-by-endpoint audit not run. |
| H6 | Unvalidated HTML in email body | **PARTIAL** | Subject CR/LF stripped to block header injection. `htmlBody` itself still passes through — bleach sanitization pending. |
| H10 | No change-password endpoint | **CHECK** | Endpoint at `backend/app/api/v1/auth.py:143` (`/auth/change-password`) verifies old password before accepting new. May have been added since the audit; please confirm. |
| H11 | Zero test coverage | **PARTIAL** | Concurrency probe added at `backend/tests/probes/concurrency_probe.py` (verifies the C2 sp_getapplock fix). Broader suite still absent. |

### New issues found and fixed this session

| ID | Issue | Severity | Fix | Reference |
|---|---|---|---|---|
| N1 | IDOR in quotation versions endpoint | Critical | Routed through `_get_quot_or_403` so F2/F5/F6 apply. | [`quotations.py:716`](backend/app/api/v1/quotations.py#L716) |
| N2 | Mass-assignment in `PUT /users/{id}` | High | Added explicit `_USER_UPDATE_ALLOWED` allowlist. | [`users.py:414-432`](backend/app/api/v1/users.py#L414-L432) |
| N3 | Cross-company role-mappings allowed | High | Pre-validates target user belongs to caller's company. | [`users.py:481-512`](backend/app/api/v1/users.py#L481-L512) |
| N4 | Email send-quotation IDORs | High | Quotation now goes through access pipeline; contact filtered by `companyId`. | [`email.py`](backend/app/api/v1/email.py) |
| N5 | Public `StaticFiles` mount bypassing tenant checks | High | Mount removed; all file reads through auth-checked asset endpoint; path-containment added in local storage service. | [`main.py:48-55`](backend/app/main.py#L48-L55), [`local_storage_service.py:26-43`](backend/app/services/local_storage_service.py#L26-L43) |
| N6 | XSS via placeholder substitution in quotation print | High | `escapeHtml` applied to all user-data placeholders + `buildLineItemsHtml` / `buildTncHtml` interpolations. | [`quotation-print.component.ts`](frontend/src/app/features/quotations/quotation-print/quotation-print.component.ts) |
| N7 | Currency loss via float math in TP-cost path | Critical | Added `get_tp_cost_decimal()` (Decimal-native); viability path now uses it; float wrapper retained only for read-only API responses. | [`costing_service.py`](backend/app/services/costing_service.py), [`viability_service.py:94`](backend/app/services/viability_service.py#L94) |
| N8 | Quotation/enquiry number race under concurrency | Critical | Serialized allocation via SQL Server `sp_getapplock`, keyed per (kind, company, userCode, fy). Verified by `concurrency_probe.py`. | [`number_allocator.py`](backend/app/services/number_allocator.py), [`quotations.py:480`](backend/app/api/v1/quotations.py#L480), [`enquiries.py:300`](backend/app/api/v1/enquiries.py#L300) |
| N9 | `canEditNumber` permission flag not enforced | High | Both create handlers now gate user-supplied `quotNo`/`enqNo` on the flag. Backfill migration grants the new gate to anyone with `canAdd`. | [`quotations.py:444`](backend/app/api/v1/quotations.py#L444), [`enquiries.py:269`](backend/app/api/v1/enquiries.py#L269), migration `v3w4x5y6z7a8` |
| N10 | `canApproveViability` permission flag not enforced | High | Viability approve endpoint now requires the granular flag (was using broad `CanApprove`). Same backfill migration. | [`viability.py:309`](backend/app/api/v1/viability.py#L309) |
| N11 | Role-menu permission save silently reset missing fields | High | Save handler now uses `model_dump(exclude_unset=True)` — absent fields preserved. Schema rejects unknown fields. Front-end payloads broadened on both v1 and v2 pages as defense in depth. | [`menus.py:288-441`](backend/app/api/v1/menus.py#L288-L441), `frontend/src/app/features/roles/role-menu-mapping*/...` |
| N12 | Dia/Length print rendering as `"NaN"` for alphanumeric values | Medium | `formatDimension` rewritten as string passthrough; type interface aligned with DB (`string \| null`); `formatPrintNumber` guard hardened. Dimension-decimals UI control removed. | [`quotation-print.component.ts`](frontend/src/app/features/quotations/quotation-print/quotation-print.component.ts), [`print-style.helpers.ts`](frontend/src/app/features/quotations/quotation-print/print-style.helpers.ts), [`quotation-format-dialog.component.ts`](frontend/src/app/features/assets/quotation-format/quotation-format-dialog.component.ts) |
| N13 | Second-cycle Submit & Mature picking wrong PO | High | (A) `submit_po` + `reject_po` now use a cycle-aware `get_submit_target_po`. (B) New cycle-scoped endpoints `PUT /cycles/{cId}/purchase-orders/{poId}/submit\|reject`; front-end migrated to them. | [`purchase_order_service.py`](backend/app/services/purchase_order_service.py), [`cycles.py`](backend/app/api/v1/cycles.py), [`quotation-form.component.ts`](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts) |
| N14 | Multi-cycle Reject incorrectly un-Converted quotation | High | `reject_po_in_cycle` only un-Converts when no other cycle still holds a Submitted formal PO. | [`purchase_order_service.py`](backend/app/services/purchase_order_service.py) |
| N15 | Annexure edit-after-approval race | High | `_get_annexure_or_403(..., for_update=True)` added; both mutating endpoints lock the row before reading status. | [`annexure.py`](backend/app/api/v1/annexure.py) |
| N16 | Self-approval on annexures (SoD breach) | High | `approve_annexure` blocks when `ann.createdby == ctx.user_id` (SuperAdmin retains break-glass). | [`annexure.py:approve_annexure`](backend/app/api/v1/annexure.py) |
| N17 | Activity log accepted caller-supplied user_id | High | `log_action` / `log_failure` now accept `ctx` and derive user from it; warning logged on disagreement. Annexure router fully migrated. | [`activity_log_service.py`](backend/app/services/activity_log_service.py), [`annexure.py`](backend/app/api/v1/annexure.py) |
| SF1 | **Soft-flow infrastructure**: approval snapshot tables + migration | Design | Adds `QuotViabilityApprovalSnapshot` + `QuotAnnexureApprovalSnapshot` so the head row can stay editable post-approval without losing the "what was signed off" answer. | [`approval_snapshot.py`](backend/app/models/approval_snapshot.py), migration `c0d1e2f3g4h5`, [`approval_snapshot_service.py`](backend/app/services/approval_snapshot_service.py) |
| SF2 | **Soft-flow snapshot-on-approval**: viability + annexure approve handlers | Design | Each `/approve` (and re-approve) call writes a frozen JSON snapshot of the row + children at that instant. Re-approval no longer early-returns — a fresh snapshot is captured every time. | [`viability.py:approve`](backend/app/api/v1/viability.py), [`annexure.py:approve_annexure`](backend/app/api/v1/annexure.py) |
| SF3 | **Soft-flow editability**: drop `_ensure_editable` lock | Design | The Approved-gate on viability + annexure edits is removed. Edits to a post-approval row succeed and append an "(after approval)" entry to the audit log. The N15 row-lock for concurrent serialization is retained. | [`viability.py:_ensure_editable`](backend/app/api/v1/viability.py), [`annexure.py:update_annexure`](backend/app/api/v1/annexure.py) |
| SF4 | **Soft-flow Round 4 deliberately deferred** (lifecycle gates kept) | Decision (2026-05-20) | After R1-R3 the user reviewed the proposed Round 4 (relax `/convert`, `/reactivate`, PO `/submit` + `/reject`, cycle `/close` + `/abandon` to event-only handlers) and chose to **keep the lifecycle gates**. Rationale: the soft-flow intent applies cleanly to *document content* (viability lines, annexure fields), not to *lifecycle transitions* which carry meaningful semantics even with full audit. Specifically: convert/reactivate gates prevent cycles starting on Rejected/Draft quotations; PO submit/reject progression keeps the multi-cycle "un-Convert when last formal PO rejected" logic well-defined; cycle close preconditions remain a meaningful "ready to send to customer" signal. No action required — this row exists so the decision is recorded against the design history. |
| ~~SF5~~ | ~~Frontend follow-up for soft-flow visibility~~ | **FIXED 2026-05-20** — yellow approval banner added to both viability and annexure components when `status === 'Approved'`. TP-cost toggle/date + refresh path no longer gate on Approved (edits journaled). Annexure `isLocked` simplified to honour the parent `readOnly` input only. | [`quotation-viability.component.ts`](frontend/src/app/features/quotations/quotation-viability/quotation-viability.component.ts), [`quotation-annexure.component.ts`](frontend/src/app/features/quotations/quotation-annexure/quotation-annexure.component.ts) |
| ~~SF6~~ | ~~Snapshot retrieval API~~ | **FIXED 2026-05-20** — three GET endpoints per entity: `/approval-snapshots` (list), `/approval-snapshots/latest` (most recent + body), `/approval-snapshots/{id}` (specific historical snapshot). Tenant-scoped via the parent's `_get_*_or_403` access check. | [`viability.py`](backend/app/api/v1/viability.py), [`annexure.py`](backend/app/api/v1/annexure.py), [`schemas/approval_snapshot.py`](backend/app/schemas/approval_snapshot.py) |
| SF7 | **Soft-flow Slice A — FWS Approve workflow (D1-D6 design)** | **DONE 2026-05-20** — `QuotFWSApprovalSnapshot` table + migration `d1e2f3g4h5i6`. Per-cycle `versionNo` (unique constraint backstops concurrent-approve races). `approve_fws` service with D3 content-hash short-circuit (re-approve with no changes = audit event only, no new version). `POST /quotations/{qid}/cycles/{cId}/fws/approve` endpoint, race-loss maps to 409. Three GET endpoints (list / latest / by-id), one POST restore endpoint that deserializes a snapshot back into the live FWS rows with type-coerced Decimal/Date/DateTime values. Display label format `C{cycleNo}-V{versionNo}` returned by the endpoints so the FE doesn't need to compose it. | [`models/approval_snapshot.py`](backend/app/models/approval_snapshot.py), [`services/approval_snapshot_service.py`](backend/app/services/approval_snapshot_service.py), [`api/v1/cycles.py`](backend/app/api/v1/cycles.py), migrations `d1e2f3g4h5i6` + `e2f3g4h5i6j7` |
| SF8 | **Soft-flow Slice A.6 — D3 parity for Viability + Annexure approve** | **DONE 2026-05-20** — `contentHash` column added to `QuotViabilityApprovalSnapshot` + `QuotAnnexureApprovalSnapshot` via migration `e2f3g4h5i6j7`. `write_viability_snapshot` / `write_annexure_snapshot` now return `SnapshotWriteResult(snapshot, created)` and short-circuit on hash-match (no duplicate-content snapshots). The two approve handlers log "(no changes)" suffix on the activity log when D3 kicks in. | [`services/approval_snapshot_service.py`](backend/app/services/approval_snapshot_service.py), [`viability.py:approve`](backend/app/api/v1/viability.py), [`annexure.py:approve_annexure`](backend/app/api/v1/annexure.py) |
| SF9 | **Remaining soft-flow slices — design decisions locked** | Partially closed | Slices A, B, C, D landed 2026-05-20 (see SF7–SF13). Remaining: E–G frontend pieces (version-picker shared component, cycle status rollup panel). |
| SF10 | **Slice B — Source-version pickers on Generate dialogs** | **DONE 2026-05-20** — Optional body params `sourcedFromFWSSnapshotId` on POST /viability and `sourcedFromViabilityId` + `sourcedFromPOId` on POST /annexure. Defaults preserve legacy behaviour. Viability now supports non-destructive sourcing from a frozen FWS snapshot (live FWS untouched). Annexure picks specific viability + PO within the cycle. | [`viability_service.py`](backend/app/services/viability_service.py), [`annexure_service.py`](backend/app/services/annexure_service.py), [`viability.py`](backend/app/api/v1/viability.py), [`annexure.py`](backend/app/api/v1/annexure.py) |
| SF11 | **Slice C — Submit & Mature retired; PO Withdrawal added** | **DONE 2026-05-20** — Four endpoints (legacy + cycle-scoped Submit/Reject) now return 410 Gone with migration guidance. New `DELETE /quotations/{qid}/cycles/{cId}/purchase-orders/{poId}` soft-deletes a PO without touching the quotation's Converted status. FE removed Submit & Mature + Reject PO buttons; replaced with a single Withdraw PO button calling the DELETE endpoint. Un-Convert cascade now unreachable (dead code in `purchase_order_service.reject_po*`). | [`quotations.py`](backend/app/api/v1/quotations.py), [`cycles.py`](backend/app/api/v1/cycles.py), [`quotation-form.component.ts`](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts) |
| SF12 | **Slice D — Cycle inheritance tightened to FWS-only** | **DONE 2026-05-20** — `get_inheritance_source` no longer returns the parent's approved viability; always returns parent FWS lines. New cycle's viability + annexure are regenerated from scratch against the inherited FWS rather than cloned from the parent's approved viability. | [`cycle_service.py:get_inheritance_source`](backend/app/services/cycle_service.py) |
| ~~SF13~~ | ~~Remaining FE work (F + G)~~ | **FIXED 2026-05-20** — both shipped, see SF15 + SF16. |
| ~~SF14~~ | (Slice E) | **DONE 2026-05-20** (entry above unchanged) |
| SF15 | **Slice G — Snapshot viewer dialog + Preview affordance** | **DONE 2026-05-20** — New shared `<app-snapshot-viewer-dialog>` that fetches any snapshot-detail URL and renders the frozen JSON as a structured key/value tree (with "Download JSON" for auditors). Version picker exposes a per-row eye-icon button that emits `(preview)` when a row carries a `previewUrl`. Both Generate dialogs wired it through: FWS snapshots get their by-id URL; the viability picker in the annexure dialog points at `/viability/{vid}/approval-snapshots/latest` so the user can verify what they're binding to before clicking Generate. | [`snapshot-viewer-dialog.component.ts`](frontend/src/app/shared/components/snapshot-viewer/snapshot-viewer-dialog.component.ts), [`version-picker.component.ts`](frontend/src/app/shared/components/version-picker/version-picker.component.ts), [`generate-viability-dialog.component.ts`](frontend/src/app/features/quotations/quotation-viability/generate-viability-dialog.component.ts), [`generate-annexure-dialog.component.ts`](frontend/src/app/features/quotations/quotation-annexure/generate-annexure-dialog.component.ts) |
| SF16 | **Slice F — Cycle status rollup panel** | **DONE 2026-05-20** — New `<app-cycle-status-panel>` mounts above the stepper. Self-fetches PO/LOI counts, FWS snapshot count + latest label, current viability + annexure status. Four colour-coded chips; click any → stepper jumps to that stage (FWS chip lands the user on the PO tab where the working sheet lives). Re-fetches automatically on cycle change. | [`cycle-status-panel.component.ts`](frontend/src/app/features/quotations/cycle-status-panel/cycle-status-panel.component.ts), [`quotation-form.component.ts`](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts) |
| SF17 | **Per-Approve `versionNo` for viability + annexure snapshots** | **DONE 2026-05-20** — `write_viability_snapshot` and `write_annexure_snapshot` now compute `versionNo = (latest snapshot's + 1) or 1` instead of mirroring the sheet/annexure row's `versionNo`. This makes the C{n}-V{m} labels advance correctly across multiple Approve clicks (V1, V2, V3, …) as the user's design intends. FWS already worked this way; viability + annexure now match. Existing snapshots written before this change keep their original `versionNo` (data-quality artifact — acceptable since SF8 only just landed). | [`approval_snapshot_service.py`](backend/app/services/approval_snapshot_service.py) |
| SF14 | **Slice E — Shared version picker + Generate dialogs** | **DONE 2026-05-20** — New reusable `<app-version-picker>` component (radio-list with `C{n}-V{m}` labels, approval ✓ badges, approver/timestamp meta). Two Generate dialogs wired to it: viability Re-generate now opens a dialog with a FWS snapshot picker (includes a "Live FWS" synthetic option as the default); annexure Generate opens a dialog with a viability + PO/LOI picker scoped to the current cycle. Cycle context wired through from parent (`selectedCycleNo` getter) so dialogs can render proper `C{n}-V{m}` labels. Lazy `import()` keeps the dialog code out of the eager bundle. | [`version-picker.component.ts`](frontend/src/app/shared/components/version-picker/version-picker.component.ts), [`generate-viability-dialog.component.ts`](frontend/src/app/features/quotations/quotation-viability/generate-viability-dialog.component.ts), [`generate-annexure-dialog.component.ts`](frontend/src/app/features/quotations/quotation-annexure/generate-annexure-dialog.component.ts), [`quotation-viability.component.ts`](frontend/src/app/features/quotations/quotation-viability/quotation-viability.component.ts), [`quotation-annexure.component.ts`](frontend/src/app/features/quotations/quotation-annexure/quotation-annexure.component.ts), [`quotation-form.component.ts`](frontend/src/app/features/quotations/quotation-form/quotation-form.component.ts) |

### UI/UX hardening (not bug-class but session-scope)

- **Unlock & Edit affordances hidden across all 4 stages.** `unlockEditHidden = true` flag on each component; Restore / Re-source (which share the same permission gate) remain visible to permitted users.
- **Dimension Decimals control removed** from the quotation-format dialog since dia/length are alphanumeric. Saved-settings field preserved for back-compat.

---

## Open issues (current)

### Critical (still open)

| ID | Issue | Notes |
|---|---|---|
| C1 | Plaintext SMTP passwords in DB | Deferred. Encrypt with Fernet or move to secrets vault. |
| C4 | JWT tokens stored in `localStorage` | Deferred per user — multi-day project (httpOnly cookies + CSRF strategy + IIS reverse-proxy cookie path). |
| C5 | No CSRF protection | Couples with C4 fix. |

### High (still open)

| ID | Issue | Notes |
|---|---|---|
| H1 | Internal error details leaked in responses | `str(e)` returned to clients in several places. |
| H2 | No rate limiting beyond login | |
| H3 | No file upload size limit for `general` category | |
| H4 | Email sending is synchronous | Blocks request thread. |
| H5 | No circular-reference guard on quotation revision chain | |
| H7 | Soft-delete bloat — no cleanup policy | |
| H8 | SMTP config readable by anyone with DB access | Same root as C1. |
| H9 | Mutual `reportTo` loop possible | |
| H11 | Zero test coverage (partial) | One probe added; broader suite missing. |
| ~~N15~~ | ~~Annexure edit-after-approval race~~ | **FIXED 2026-05-20** — `_get_annexure_or_403` now accepts `for_update=True`; both approve and update endpoints lock the row before reading status. |
| ~~N16~~ | ~~Self-approval allowed on annexures~~ | **FIXED 2026-05-20** — `approve_annexure` rejects when `ann.createdby == ctx.user_id` (SuperAdmin break-glass retained). |
| ~~N17~~ | ~~`activity_log_service.log_action` accepts arbitrary `actionByUserId`~~ | **PARTIAL FIX 2026-05-20** — `log_action` / `log_failure` now accept `ctx` (preferred) and derive `user_id` from it, ignoring any caller-supplied value. Disagreement is logged as a warning. Annexure router fully migrated as proof-of-pattern. See **N17b** below for the mechanical migration of the other ~50 callers. |
| N17b | Migrate remaining `log_action` / `log_failure` callers to pass `ctx` | ~50 sites across `quotations.py`, `cycles.py`, `assets.py`, `viability.py` still pass `user_id=ctx.user_id` rather than `ctx=ctx`. The new helper accepts both shapes, so they're not broken — but the integrity guarantee only kicks in once they use `ctx`. Mechanical find-and-replace. |
| N18 | KPI Studio: SQL doesn't auto-enforce tenant filter | Validator rejects DDL/DML/sys-table access but doesn't require `company_id = :company_id` in user-authored SELECTs. |
| N19 | Cursor pagination breaks on non-unique sort columns | Pages overlap/skip when sort by `quotDate`, `status`, etc. Composite cursor needed. |
| N20 | Soft-deleted rows leak into TP cost scheduler | Updates run over `QuotDetails` without `isActive == True`. |

### Medium (still open)

All M1–M14 from original audit remain open. New additions:

| ID | Issue | Notes |
|---|---|---|
| N21 | Email header injection elsewhere | `/send-quotation` fixed; audit other email paths if/when added. |
| N22 | Excel formula injection on export | `quotation_excel_service` and `viability_excel_service` write user strings without prefixing `'` on values starting with `=+@-\t\r`. |

### Schema (new class — 2026-05-05)

| ID | Issue |
|---|---|
| S1 | `RoleMenuMap` has no unique on `(roleId, menuId)` — duplicates create non-deterministic permission checks. |
| S2 | Master table names not unique per company (ItemGrade, DeliveryMode, DeliveryTerm, ContactType, CostPointMaster, TermsNConditionMaster). |
| S3 | `RawMaterialCost (companyId, dia, effectedFrom)` not unique — TP-cost lookup picks arbitrarily. |
| S4 | `UserRoleMap` / `UserLocationMap` lack composite uniques — duplicate permissions/locations possible. |
| S5 | `QuotSummary.quotNo / quotDate / status / ownerUserId` nullable when business rules say they shouldn't be. NULL `ownerUserId` is invisible to F5 hierarchy filter. |
| S6 | `QuotDetails` cost columns nullable — `SUM(totAmount)` silently undercounts. |
| S7 | `AuditMixin.createdon` Python-only default — raw-SQL inserts get NULL timestamps. |
| S8 | `AuditMixin.lastupdateon` Python-only `onupdate` — raw-SQL UPDATEs leave it stale. |

Diagnostic queries to run before scaffolding fixes:

```sql
-- S1: existing dupes
SELECT roleId, menuId, COUNT(*) FROM RoleMenuMap GROUP BY roleId, menuId HAVING COUNT(*) > 1;

-- S2: dupes (run per master table)
SELECT companyId, itemGradeName, COUNT(*) FROM ItemGrade
 WHERE isActive = 1 GROUP BY companyId, itemGradeName HAVING COUNT(*) > 1;

-- S5: nullable-but-should-not-be counts
SELECT
  SUM(CASE WHEN quotNo      IS NULL THEN 1 ELSE 0 END) AS null_quotNo,
  SUM(CASE WHEN quotDate    IS NULL THEN 1 ELSE 0 END) AS null_quotDate,
  SUM(CASE WHEN status      IS NULL THEN 1 ELSE 0 END) AS null_status,
  SUM(CASE WHEN ownerUserId IS NULL THEN 1 ELSE 0 END) AS null_owner
FROM QuotSummary WHERE isActive = 1;
```

### Low (still open)

All L1–L8 from original audit remain open.

---

## Suggested next slices (ranked)

1. **Schema constraints (S1–S3 first)** — short migrations, high leverage, fix once. Run the diagnostic queries to know dedupe scope.
2. **N15 + N16 (annexure approval race + self-approval)** — both touch the workflow the Commercial HOD role was added to enforce. Small fix, high reputational value.
3. **N17 (activity-log integrity)** — make the audit trail trustworthy. Required precondition for compliance reviews.
4. **N18 (KPI Studio tenant filter)** — before NL→SQL goes to non-SuperAdmin users.
5. **C4 + C5 (JWT migration)** — its own branch/PR, scheduled.
6. **Removal of legacy `/purchase-order/submit\|reject`** — one release after the multi-cycle migration settles (mid-2026-05 timeframe).

---

---

## Original audit (2026-04-26) — preserved verbatim

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
