# Multiple Purchase Orders + LOI-driven Viability — Change Request

> ## ⚠️ SUPERSEDED
> This draft has been replaced by [`MultiplePO-LOI-Cycle-CR.md`](MultiplePO-LOI-Cycle-CR.md)
> (2026-05-18). The new doc covers everything here plus the **Call-off Cycle**
> grouping, rate inheritance across cycles, ad-hoc items mid-cycle, and the
> Phase 1A–1G implementation plan. Read the new doc; the content below is
> retained only for archival reference.
> ---
>
> **Status (original):** Planning. Decisions 1-7 still open. No code changed yet.
> **Captured (original):** 2026-05-11

## The three asks (verbatim from the user)

> Uploading of Purchase Order:
> - Multiple Purchase Orders (POs) / amendments of PO should be allowed against a single
>   quotation, even after approval of the viability sheet. Currently, only a single PO can be uploaded.
> - Generation of the viability sheet is presently restricted until uploading of the PO.
> - It was suggested that viability preparation should also be allowed based on uploading of the
>   Letter of Intent (LOI) for faster action of commercial team and PO will be uploaded later.

### Restated

1. **Multi-PO per quotation.** Drop the current 1:1 constraint. Multiple distinct POs against one quotation, plus PO amendments. Adding new POs must work **even after the viability sheet is approved**.
2. **Earlier viability trigger via LOI.** Today viability is gated on PO submission. The commercial team wants to start viability work as soon as an **LOI** arrives, with the actual PO uploaded later.
3. **Workflow knock-on:** the stepper, annexure, and approvals all need to behave coherently when there are N POs (some amended, some superseded by an LOI followed by a real PO, etc.).

## Current state, for reference

| Stage | Entity | Multiplicity | Source for next stage |
|---|---|---|---|
| Quotation | `QuotSummary` | 1 | `QuotDetails` |
| PO | `QuotPurchaseOrder` | **1 per quotation** (UNIQUE filtered idx on quotId) | `QuotPOWorkingSheet` |
| Viability | `QuotViabilitySheet` | 1 per quotation | `QuotPOWorkingSheet` |
| Annexure | `QuotAnnexure` | 1 per quotation | viability + PO |

Within each stage, `parentXxxId / versionNo` already supports versioning (amendments). The gap is **cardinality** — multiple *distinct* POs (and downstream artifacts) per quotation.

## Proposed design — two-axis model

Separate **amendment** (versioning) from **distinct PO** (cardinality).

```
Quotation (1)
 ├─ PO #1 ──── amendment v1 → v2 → v3 (head)
 │   ├─ Working Sheet (latest version)
 │   ├─ Viability Sheet (own version chain)
 │   └─ Annexure (own version chain)
 ├─ PO #2 ──── single version (head)
 │   ├─ Working Sheet
 │   ├─ Viability Sheet
 │   └─ Annexure
 └─ PO #3 ──── (LOI, isLOI=True)
     ├─ Working Sheet (qty from LOI)
     ├─ Viability Sheet (computed from LOI qty)
     └─ Annexure (optional — usually generated after LOI upgrades to real PO)
```

- **Amendments** stay on the existing `parentPOId / versionNo` chain.
- **Distinct POs** sit side-by-side, each with their own viability + annexure chain.
- **LOI** = `QuotPurchaseOrder` row with `isLOI=True`. Optional flag → no new table. When the actual PO arrives, two options (Decision 1): upgrade in place, or create a sibling PO and link via `loiUpgradedFromPOId`.

## What changes

### Backend
- **Drop the UNIQUE filtered index** on `QuotPurchaseOrder.quotId`.
- **Move viability + annexure FKs from `quotId` to `poId`**. Existing rows backfill via the (currently unique) PO row.
- New columns on `QuotPurchaseOrder`:
  - `isLOI BIT NOT NULL DEFAULT 0`
  - `loiUpgradedFromPOId INT NULL FK→self`
  - `poTitle NVARCHAR(100) NULL` — label like "PO #1 - Plant A"
- **Viability gate** changes: viability can be generated against any PO that is either `Submitted` *or* `isLOI=True`. Drop the "must be the only PO" rule.
- New endpoint `GET /quotations/{id}/purchase-orders` (list) — replaces the single-PO GET.
- `POST /quotations/{id}/purchase-orders/{poId}/upgrade-loi` — flips an LOI to a real PO (or creates a sibling PO and links back, depending on Decision 1).

### Frontend
- **Stage 2 becomes a list view** of POs for that quotation, with "Add PO" / "Upload LOI" buttons. Each row shows PO number / date / status / isLOI badge / has-viability badge / has-annexure badge.
- Clicking a PO opens the existing Stage 2 dialog (PO edit + Final Working Sheet + Submit/Reject toolbar).
- **Stages 3 & 4 (Viability, Annexure) become per-PO sub-tabs.** Selecting "PO #2" shows that PO's viability and annexure stages.
- **Stepper** flattens "Stage 2-3-4" into "Purchase Orders" with a per-PO breakdown drilldown.

### Lifecycle invariants preserved
- Per-stage versioning chain (`parentXxxId / versionNo`) — already there, just scoped per-PO now.
- Unlock & Edit with audit (`LifecycleUnlockAudit`) — extends naturally; audit gains `poId` column.
- Soft delete + `isActive` for POs that get cancelled.

## Open decisions (need user picks before scoping)

| # | Decision | Recommendation |
|---|---|---|
| 1 | **LOI upgrade behavior** — when the actual PO arrives, do we (a) flip the LOI row in place to `isLOI=False`, or (b) create a sibling PO and link back to the LOI via `loiUpgradedFromPOId`? | (a) **Upgrade in place** for simplicity; audit columns track who changed what. |
| 2 | **Viability/Annexure cardinality** — per-PO (each PO has its own chain) vs. per-quotation (one chain summarising all POs)? | **Per-PO** — more flexible, matches commercial team's mental model. |
| 3 | **Sibling-PO staleness** — when a new PO arrives after a viability is already approved on a different PO, does the old viability get a "stale" banner? | **No** — viabilities are per-PO, siblings don't make each other stale. Stale only when the upstream *quotation* revises. |
| 4 | **LOI viability approvability** — can the LOI's viability be formally approved, or is it review-only? | **Approvable** — commercial team needs to lock in margin analysis early; if PO terms differ later, that's a new viability anyway. |
| 5 | **Annexure off LOI** — can an annexure be generated against an LOI, or only after upgrade? | **Only after LOI upgrades to a real PO** — annexures are customer-facing legal-style docs; premature off an LOI. |
| 6 | **Backward compat for legacy 1-PO quotations** — silent (existing PO becomes PO #1, "Add PO" appears), or with an explanatory banner? | **Silent** — banner adds noise; users will discover the button. |
| 7 | **Permissions** — flat (any user with `CanSubmitPO` / `CanApproveViability` etc. can act on any PO under a visible quotation), or per-PO ownership? | **Flat** — quotation ownership already gates visibility; no stated use case for per-PO ownership. |

## Suggested phasing

| Phase | Scope | Shippable independently? |
|---|---|---|
| **Phase A — Backend + data model** | Drop UNIQUE constraint; add `isLOI` / `loiUpgradedFromPOId` / `poTitle`; migrate viability + annexure FKs from `quotId` to `poId`; new list endpoint. **No UI change** — single-PO continues to work. | ✅ |
| **Phase B — UI: PO list view** | Stage 2 becomes a list; Stages 3 & 4 become per-PO drilldowns; add "Upload LOI" button. Existing single-PO quotations transparently render as a 1-row list. | ✅ |
| **Phase C — LOI upgrade flow** | Wire the LOI → real PO upgrade button; LOI-driven viability path. | ✅ |

## Out of scope (future)

- Compare-versions diff view between PO amendments.
- Per-PO email notifications.
- Multi-company POs (a single quotation receiving POs from different buyer legal entities).
- Auto-merge: combining quantities from multiple POs into a single viability.

## Verification (to be written after design is locked)

Each phase will get its own E2E check — to be detailed once the 7 decisions are resolved.

---

End of plan.
