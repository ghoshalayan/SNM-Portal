# Multiple PO + LOI + Call-off Cycle — Change Request

> **Status:** Approved for implementation (Phase 1 of the SNM Portal roadmap).
> **Captured:** 2026-05-18.
> **Supersedes:** `MultiplePO-CR.md` (2026-05-11).
> **Companion:** Phase 0 (foundation refactor — tests, logging, queue) lands before this CR's code.

---

## 1. Business need

The lifecycle today is single-PO per quotation. That maps cleanly to dealer / SMB customers but cannot model how Indian primary-steel manufacturers actually sell to EPC contractors, government projects, and large private buyers:

1. **LOI before PO.** Large buyers issue a Letter of Intent first — non-binding by default under Indian law but operationally treated as green-light. The supplier kicks off production planning and margin work on the strength of the LOI; the formal PO arrives later.
2. **Multiple LOIs / POs per quotation.** Same quotation supports months/years of supply through a series of **call-offs** (each call-off is another LOI or PO drawn against the master rate contract).
3. **Ad-hoc items mid-cycle.** Customers add new dias / new items inside an LOI/PO that weren't in the original quoted BOM.
4. **Annexure stands on LOI basis.** Once the annexure (price schedule) is issued off an LOI, late-arriving POs typically don't trigger annexure regeneration unless terms diverge materially.
5. **Rate inheritance across cycles.** Subsequent cycles default rates from the previous cycle's approved viability so the system "circulates" the quotation without re-quoting.

The existing `QuotPurchaseOrder.quotId UNIQUE` constraint blocks all of this. We need a deeper restructure than just dropping the index.

---

## 2. Locked design decisions

Captured during planning; baked into this CR. Override anywhere requires re-planning.

| ID | Decision | Locked value | Rationale |
|---|---|---|---|
| **C1** | Naming of the new grouping entity | Table `QuotOrderCycle`; UI label **"Call-off"** | Industry vocab; backend stays neutral so UI text can evolve. |
| **C2** | Scope of WS / Viability / Annexure | **Per cycle** (one each per cycle, not per PO) | Storybook says annexure based on LOI stands when PO arrives → cycle is the natural unit. |
| **C3** | LOI → PO arrival semantics | **Append** (LOI row stays, new PO row added) | Both documents legally exist; preserve audit. |
| **C4** | Rate inheritance source for cycle N | **Last approved viability** of cycle N-1; fallback to its working sheet if no approved viability | Approved viability is the "committed margin" state. |
| **C5** | Cycle close trigger | **Explicit user action** | Automatic close surprises users; explicit "Close Cycle" is a deliberate audit event. |
| **C6** | Multi-tenancy hardening | **RLS-ready table template from Phase 0**, RLS policies activated in Phase 5 | Designing tables RLS-ready from day one is cheap; retrofitting is expensive. |
| **C7** | JSON vs structured columns | **JSON only for heterogeneous payloads** (notification payloads, archive snapshots, saved filter criteria). Structured for everything else. | Queryability + schema validation. |
| **C8** | Document attachments | **Extend existing `Asset` table** with `linkedEntityType`, `linkedEntityId`, `category` | Avoid duplicate file-reference table. |
| **C9** | Approval workflow shape | **Simple model**: one policy → one approver role threshold | Workflow engine overkill for current needs; schema supports expansion later. |
| **C10** | API back-compat horizon | **One release aliasing** old single-PO endpoints, hard removal in the next release | Indefinite aliases never get removed. |

---

## 3. Target state

### 3.1 Conceptual model

```
QuotSummary (1)
   ├── QuotOrderCycle (N)
   │      ├── QuotPurchaseOrder (N) — LOIs (isLOI=true) + POs (isLOI=false)
   │      ├── QuotPOWorkingSheet (N rows, one Working Sheet per cycle)
   │      ├── QuotViabilitySheet (1 per cycle, with own version chain)
   │      └── QuotAnnexure       (1 per cycle, with own version chain)
   │
   └── parent quotation status / state stays at Stage 1 level
```

### 3.2 Status state machines

| Entity | States | Transitions |
|---|---|---|
| `QuotSummary` | Draft → Approved → Converted → Revised / Reject | `Converted` semantics broaden: "≥ 1 cycle started". |
| `QuotOrderCycle` | **Active → Complete** \| **Abandoned** | Complete = annexure approved + ≥ 1 PO captured + explicit "Close" action. Abandoned = explicit user action. |
| `QuotPurchaseOrder` | Draft → Submitted → Rejected | Same for LOI (`isLOI=True`). |
| `QuotViabilitySheet` | Draft → Approved | Per-cycle; can re-open via Unlock & Edit. |
| `QuotAnnexure` | Draft → Approved | Per-cycle; re-open via Unlock & Edit; stale-banner on PO divergence. |

### 3.3 Inheritance lineage

`QuotOrderCycle.parentCycleId` references the cycle whose rates were inherited at this cycle's start. Forms a linear chain per quotation (cycle 1 → 2 → 3 → …). NULL for the first cycle.

---

## 4. Data model changes

### 4.1 New table — `QuotOrderCycle`

```
QuotOrderCycle
  quotOrderCycleId   INT PK identity
  companyId          INT FK → Company.companyId   NOT NULL
  quotId             INT FK → QuotSummary.quotId  NOT NULL
  cycleNo            INT                           NOT NULL    -- sequential per quotation, starts at 1
  status             VARCHAR(20)                   NOT NULL    -- 'Active' | 'Complete' | 'Abandoned'
  parentCycleId      INT FK → QuotOrderCycle.quotOrderCycleId  NULL
  startedOn          DATETIME                      NOT NULL
  startedBy          INT FK → UserMaster.userId    NOT NULL
  closedOn           DATETIME                      NULL
  closedBy           INT FK → UserMaster.userId    NULL
  notes              NVARCHAR(500)                 NULL
  + AuditMixin (createdon, createdby, lastupdateon, lastupdateby, isActive)

Indexes:
  UNIQUE (quotId, cycleNo) WHERE isActive = 1
  IX_QuotOrderCycle_quotId_status (quotId, status)
  IX_QuotOrderCycle_companyId (companyId)   -- RLS-ready
```

### 4.2 Modifications to existing tables

| Table | Columns added |
|---|---|
| `QuotPurchaseOrder` | `isLOI BIT NOT NULL DEFAULT 0`, `loiSequence INT NULL`, `quotOrderCycleId INT FK NOT NULL` (after backfill) |
| `QuotPOWorkingSheet` | `quotOrderCycleId INT FK NOT NULL` (after backfill) |
| `QuotViabilitySheet` | `quotOrderCycleId INT FK NOT NULL` (after backfill) |
| `QuotAnnexure` | `quotOrderCycleId INT FK NOT NULL` (after backfill) |
| `LifecycleUnlockAudit` | `quotOrderCycleId INT FK NULL` (nullable; pre-cycle audits don't have one) |
| `RoleMenuMap` | `CanCaptureLOI BIT NOT NULL DEFAULT 0`, `CanStartNewCycle BIT NOT NULL DEFAULT 0` |

### 4.3 Constraint changes

- **DROP** the existing `UNIQUE filtered idx` on `QuotPurchaseOrder.quotId WHERE isActive=1`.
- **ADD** indexes on the new `quotOrderCycleId` FKs in each child table.

### 4.4 Backfill strategy

Run inside the same migration as the schema additions:

1. For every quotation in `QuotSummary` with `status = 'Converted'` or downstream artifacts:
   - Insert one `QuotOrderCycle` row with `cycleNo = 1`, `status` derived from current state (Active if any stage is Draft, Complete if annexure is Approved, Abandoned never auto-assigned), `parentCycleId = NULL`.
   - Update the existing `QuotPurchaseOrder`, `QuotPOWorkingSheet`, `QuotViabilitySheet`, `QuotAnnexure`, `LifecycleUnlockAudit` rows for that quotation to point to the new cycle.
2. Quotations without downstream artifacts (still Draft / Approved): no cycle row created; cycle is opened on first Convert call.

After backfill, `quotOrderCycleId` on the four child tables becomes `NOT NULL` (separate `ALTER COLUMN` statement at the end of the migration).

---

## 5. API surface changes

### 5.1 New endpoints

| Endpoint | Purpose | Permission |
|---|---|---|
| `GET /quotations/{qid}/cycles` | List all cycles for a quotation | `Quotations.CanRead` |
| `POST /quotations/{qid}/cycles` | Start a new cycle on an existing Approved/Converted quotation | `CanStartNewCycle` |
| `GET /quotations/{qid}/cycles/{cId}/bundle` | One-shot fetch: cycle metadata + FWS rows + viability + annexure + cycle PO/LOI list | `Quotations.CanRead` |
| `POST /quotations/{qid}/cycles/{cId}/close` | Close cycle (status → Complete) | `CanStartNewCycle` (reused; no separate flag) |
| `POST /quotations/{qid}/cycles/{cId}/abandon` | Abandon cycle (status → Abandoned) | `CanStartNewCycle` |
| `POST /quotations/{qid}/cycles/{cId}/purchase-orders` | Append PO or LOI to a cycle | `CanSubmitPO` for PO, `CanCaptureLOI` for LOI |
| `PUT /quotations/{qid}/cycles/{cId}/purchase-orders/{poId}` | Edit PO/LOI inside a cycle | `CanEdit` |
| `POST /quotations/{qid}/cycles/{cId}/purchase-orders/{poId}/submit` | Mature PO/LOI → matures Stage 2 of the cycle | `CanSubmitPO` |
| `POST /quotations/{qid}/cycles/{cId}/purchase-orders/{poId}/reject` | Reject a PO/LOI | `CanRejectPO` |
| `GET / POST / PUT  /quotations/{qid}/cycles/{cId}/working-sheet[…]` | Cycle-scoped FWS CRUD | `CanEdit` |
| `POST /quotations/{qid}/cycles/{cId}/viability` | Generate viability for a cycle | `CanEdit` |
| `GET /quotations/{qid}/cycles/{cId}/viability` | Read viability for a cycle | `CanRead` |
| `PUT /viability/{vid}/lines/{lid}` | Edit a viability line (unchanged path, sheet already cycle-scoped) | `CanEdit` |
| `POST /viability/{vid}/refresh-tp-cost` | TP-Cost refresh (unchanged; already cycle-scoped via sheet's `quotOrderCycleId`) | `CanEdit` |
| `POST /viability/{vid}/approve` | Approve cycle viability | `CanApproveViability` |
| `POST /quotations/{qid}/cycles/{cId}/annexure` | Generate cycle annexure | `CanEdit` |
| `POST /annexure/{aid}/approve` | Approve cycle annexure | `CanApproveAnnexure` |

### 5.2 Aliased / deprecated endpoints (one release only)

The existing single-PO paths return 200 with the active cycle's data, plus a `Deprecation` header pointing at the new path. Removed in the next release:

- `PUT /quotations/{qid}/purchase-order` → aliases `POST /quotations/{qid}/cycles/{activeCycleId}/purchase-orders`
- `GET /quotations/{qid}/viability` → aliases `GET /quotations/{qid}/cycles/{activeCycleId}/bundle`
- `POST /quotations/{qid}/viability` → aliases the new cycle viability generate
- `POST /quotations/{qid}/annexure` → ditto
- Etc.

Deprecation banner: `Sunset: <release-date-T+90d>`.

---

## 6. RBAC changes

### 6.1 New flags

Both added as columns on `RoleMenuMap`:

| Flag | Purpose | Default seeding |
|---|---|---|
| `CanCaptureLOI` | Capture an LOI under an active cycle | KRO+ ON by default; mirrors `CanSubmitPO` for migration parity. |
| `CanStartNewCycle` | Open a new cycle on an Approved/Converted quotation; close / abandon a cycle | HOD+ ON; KRO OFF. |

### 6.2 Semantic broadening (no flag change)

| Flag | What changes |
|---|---|
| `CanSubmitPO` | Still gates Submit & Mature, but now applies to LOIs too (LOI submit matures Stage 2). |
| `CanRejectPO` | Applies per PO/LOI within a cycle. |
| `CanConvert` | Now also creates Cycle #1 implicitly. |

### 6.3 Unlock & Edit flags

All four existing `CanUnlockEdit{Quotation,PO,Viability,Annexure}` flags remain unchanged. `LifecycleUnlockAudit` rows gain `quotOrderCycleId` for clarity (which cycle's stage was unlocked).

### 6.4 Role template seeding migration

Idempotent update to the existing `g1h2i3j4k5l6_seed_rbac_role_templates` chain (new migration appended; old migration left intact). For each company:

- `SuperAdmin`, `CompanyAdmin`: all new flags ON.
- `Director`: `CanCaptureLOI` ON, `CanStartNewCycle` ON.
- `HOD`: `CanCaptureLOI` ON, `CanStartNewCycle` ON.
- `Commercial HOD`: `CanCaptureLOI` ON, `CanStartNewCycle` OFF.
- `KRO`: `CanCaptureLOI` ON (LOI is captured by sales), `CanStartNewCycle` OFF (HOD decides when to circulate).

Custom roles get OFF defaults; admin manually grants.

---

## 7. Service layer

### 7.1 New: `cycle_service.py`

- `start_new_cycle(db, quotation, started_by, parent_cycle_id=None)` — creates the cycle row + clones FWS rows from parent's approved viability (fallback FWS).
- `close_cycle(db, cycle, user_id, reason)` — validates close preconditions (annexure approved + ≥ 1 PO captured + status=Active), flips status to Complete, writes audit log entry.
- `abandon_cycle(db, cycle, user_id, reason)` — bypasses close preconditions, status → Abandoned.
- `inherit_rates_from_parent(db, new_cycle, parent_cycle)` — per-line copy: matching (item, dia, length) from parent's viability/WS. Truly new items (no match in parent) → fresh TPWGST from RawMaterialCost master at new cycle's start date (using the existing log-aware helper).

### 7.2 Modifications

| File | Change |
|---|---|
| `purchase_order_service.py` | All functions take `cycle` instead of `quotation`. Append-only insert (drop the "find-or-update existing PO" path). |
| `po_working_sheet_service.py` | FWS clone source: cycle's parent (rates) + cycle's POs/LOIs (lines). |
| `viability_service.py` | Already cycle-aware (the TP-Cost refresh service already uses `sheet.tpCostMode` per-instance). Sheet creation now writes `quotOrderCycleId`. |
| `annexure_service.py` | Generation function takes cycle, sources from cycle's viability + PO lines. |
| `lifecycle_service.py` | Unlock audit writes include cycle ID. |

---

## 8. UX changes

### 8.1 Cycle selector strip

New horizontal strip below the Stage 1 stepper:

```
[ Cycle 1 · Complete ✓ ] [ Cycle 2 · Active ⚡ ] [ + New Call-off ]
```

- Hidden when total cycle count ≤ 1 (legacy quotations look identical to today).
- Each pill clickable; selecting a cycle filters Stages 2-3-4 to that cycle's data.
- Each pill colour-coded by status (green=Complete, blue=Active, grey=Abandoned).

### 8.2 Stage 2 (Purchase Orders / Final Working Sheet)

- Becomes a **list view** inside the selected cycle. Each row = one PO or LOI.
- New action buttons: **"Add LOI"** (`CanCaptureLOI` required) and **"Add PO"** (`CanSubmitPO` required) at the top.
- Each row shows: doc number, doc date, isLOI badge, status, "Submit & Mature" / "Reject" buttons.
- Below the list: the FWS grid (unchanged shape).

### 8.3 Stage 3 (Viability)

- No structural change; just one viability per cycle.
- The TP-Cost source toggle (already shipped) continues to work as-is.
- Cycle inheritance banner at the top when this is cycle ≥ 2: "Rates inherited from Cycle N-1's approved viability."

### 8.4 Stage 4 (Annexure)

- One annexure per cycle.
- New banner when a PO is appended to a cycle whose annexure is already Approved AND the PO qty/rate diverges from the LOI source: "Annexure was generated from LOI #X. PO #Y diverges by Z%. Click to re-source."

### 8.5 Quotation list page

New badges per quotation row:

- **Cycles:** `2`
- **Active Cycle Stage:** `Viability` / `Annexure` / etc.
- **LOIs / POs total:** `3L · 1P`

### 8.6 Cycle history tab

New top-level tab on the quotation workspace: "Cycle History" — chronological list of all cycles with their status, started/closed dates, owner, link to drill in.

---

## 9. Migration strategy

### 9.1 Forward (safe, single migration `cyc_<timestamp>`)

1. **Add new tables and columns** with `nullable=True` initially.
2. **Backfill** existing rows (single SQL UPDATE per child table).
3. **Set columns to `NOT NULL`** via separate `ALTER COLUMN` after backfill verifies.
4. **Drop** the `UNIQUE filtered idx` on `QuotPurchaseOrder.quotId`.
5. **Add** new indexes on the FKs.

### 9.2 Backward (single downgrade)

Drop new columns, drop new tables, restore the UNIQUE index. Lossy for cycle data but data integrity preserved for pre-CR state.

### 9.3 Production deploy

- Maintenance window NOT required — all changes are additive until step 3.
- Step 3 (NOT NULL alter) can run online on SQL Server with brief schema lock; tolerable on a low-traffic window.
- Frontend deploy AFTER backend so legacy single-PO clients hit aliased endpoints during the gap.

---

## 10. Internal phasing (Phase 1A → 1G)

| Sub-phase | Scope | Approx |
|---|---|---|
| **1A** | Data model + migration. No code change to services yet. Run backfill, verify legacy paths still work via aliasing. | ~1 week |
| **1B** | Service layer refactor: `cycle_service`, `purchase_order_service`, `po_working_sheet_service`. Backwards-compatible aliasing remains. | ~2 weeks |
| **1C** | API: new cycle-scoped endpoints + alias layer for legacy paths. | ~1 week |
| **1D** | Frontend: cycle selector + per-cycle Stage 2 list view + "Add LOI / Add PO" buttons. | ~2 weeks |
| **1E** | Rate inheritance service + ad-hoc item flow (Working Sheet "Add Line" allows items not in source quotation). | ~1 week |
| **1F** | Annexure stale-banner on PO divergence + Cycle History tab. | ~1 week |
| **1G** | Excel/Print updates for cycle context, activity log new action codes, deprecation banner on legacy endpoints. | ~1 week |

Total: **8-10 weeks** (one team, full-time).

---

## 11. Verification (per sub-phase)

### Phase 1A — Data model
- Existing quotations with downstream artifacts are backfilled to Cycle #1.
- Foreign keys + indexes verified via DB query.
- `alembic downgrade` round-trip clean.

### Phase 1B — Service layer
- Unit tests (from Phase 0): for each service function, both "single-cycle legacy" path and "multi-cycle new" path covered.
- Cycle creation idempotent (calling start_new_cycle twice with same parent doesn't create two cycles).

### Phase 1C — API
- Old endpoint `PUT /quotations/{id}/purchase-order` returns 200 with `Deprecation` header.
- New endpoint `POST /quotations/{id}/cycles/{cId}/purchase-orders` validates against `CanCaptureLOI` / `CanSubmitPO`.

### Phase 1D-1G — End-to-end
- **Demo flow:** create quotation → approve → convert → add LOI → submit & mature → generate viability → approve → generate annexure → approve → PO arrives → append to cycle → start cycle 2 with ad-hoc item → verify rate inheritance + new item gets fresh master rate.
- Mobile + desktop view rendering correctness.
- Excel export multi-cycle workbook.
- Cycle History tab shows all cycles for a multi-cycle quotation.

---

## 12. Out of scope (will be separate CRs)

- **Customer portal / dealer self-service** — Phase 3+ in the roadmap; not this CR.
- **E-Invoice / e-Way Bill integration** — separate compliance CR.
- **Outstanding / receivables tracking** — downstream order-to-cash; user explicitly excluded.
- **Tiered approval workflow** — Phase 2 CR.
- **Annexure validity period** — Phase 2 CR (small, schema-only addition).
- **Price-variation clause** — Phase 2 CR.
- **Volume commitment / offtake tracking** — Phase 2 CR.
- **Customer credit-risk score** — depends on receivables; out of scope here.
- **Discount approval tiers** — covered by tiered approval workflow.
- **WhatsApp / SMS notifications** — Phase 4 CR.

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Backfill misses edge cases (orphan QuotPOWorkingSheet without a viability, etc.) | Dry-run migration on production data copy; explicit handling of every orphan pattern. |
| Frontend deployed before backend → 404s on new endpoints | Standard deploy ordering: backend first. |
| Legacy API consumers don't respect `Deprecation` header → break on cut-over | One-release sunset is generous; CR doc + email to API consumers. |
| Cycle creation race condition (two users click "New Call-off" simultaneously) | `UNIQUE (quotId, cycleNo)` constraint; service uses SELECT FOR UPDATE on the quotation. |
| Goal-seek on a cycle's viability writes to wrong cycle | Foreign keys enforce; service-layer fetch always includes `quotOrderCycleId` in the where clause. |
| Permission migration breaks existing custom roles | New flags default OFF; existing custom roles unaffected. Admin manually grants new flags. |

---

## 14. Open questions (post-CR, to revisit in design review)

1. Should `parentCycleId` allow non-linear chains (cycle 3 inherits from cycle 1, skipping cycle 2)? Currently linear-only; safer to start there.
2. Should cycle close auto-trigger an end-of-cycle email to the customer (e.g. "Annexure approved, cycle closed")? Probably yes — Phase 4 (notifications) handles it.
3. Should a Cycle Status of "Abandoned" hide the cycle from default views? Yes — quotation list filter shows only Active + Complete by default; "Show Abandoned" toggle reveals.

---

## 15. Acceptance sign-off

- **Functional:** PM / Commercial HOD signs off on the end-to-end demo flow.
- **Data:** DBA reviews migration on production-copy DB; signs off on backfill correctness.
- **RBAC:** Internal audit reviews new permission flags + role-template seeding.
- **API:** API consumer survey confirms migration of any third-party integrations within the one-release window.

---

End of CR.
