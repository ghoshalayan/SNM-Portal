"""Final Working Sheet (Stage-2 BOM) service.

Owns the create-clone, line CRUD, and edit-lock semantics for
``QuotPOWorkingSheet``. The route layer stays thin: it enforces RBAC,
calls in here for the business rules, and surfaces our exceptions as
HTTP errors.

Edit gate: lines are mutable while ``QuotPurchaseOrder.status ==
'Draft'``. Once Submit & Mature fires the rows are snapshotted —
attempts to edit afterwards raise ``WorkingSheetLockedError`` and the
route layer maps that to HTTP 409. The privileged Unlock-and-Edit
path is the escape valve.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.quot_po_working_sheet import QuotPOWorkingSheet
from app.models.quot_purchase_order import QuotPurchaseOrder
from app.models.quotation import QuotDetails, QuotSummary
from app.schemas.quot_po_working_sheet import QuotPOWorkingSheetLineBody


# Editable while PO is Draft. Once Submitted / Rejected the lines are
# locked; admins use Unlock-and-Edit (audited) to re-open.
_LINE_EDITABLE_PO_STATUSES = {"Draft"}


# Columns copied verbatim on clone. Mirrors QuotDetails. Keep this list
# in sync if either model adds a new cost head.
_CLONE_COLUMNS = (
    "itemid", "itemName", "itemGradeName", "itemDia",
    "itemLength", "itemUnit", "quantity",
    "TPWGST", "Marketing", "FreightTrailer", "FreightTruck",
    "Unloading", "OHD", "IFC", "WeighmentDiff", "CD",
    "SWECharge", "CRS", "IncCharge", "ShortLnthCharge",
    "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
    "Commission", "Misc", "Testing", "MOUTOD", "SplDisc", "JC",
    "modeOfDispatch",
    "basicRate", "totRate", "gstMode",
    "IGST", "CGST", "SGST", "totAmount",
)


class WorkingSheetLockedError(RuntimeError):
    """Line CRUD attempted on a non-Draft PO. Translated to 409."""


class WorkingSheetNotFoundError(LookupError):
    """Specific line ID not found / not active. Translated to 404."""


def list_lines(db: Session, po: QuotPurchaseOrder) -> List[QuotPOWorkingSheet]:
    return (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.quotPOId == po.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712 — SQL Server compat
        )
        .order_by(QuotPOWorkingSheet.poWorkingSheetId.asc())
        .all()
    )


def clone_from_quotation(
    db: Session,
    po: QuotPurchaseOrder,
    quotation: QuotSummary,
    *,
    user_id: int,
) -> List[QuotPOWorkingSheet]:
    """Idempotent. Clones every active ``QuotDetails`` row into a
    matching ``QuotPOWorkingSheet`` row linked to ``po``. If the PO
    already has any active lines (re-Convert after Reject, or repeat
    call) we skip to keep the user's intermediate edits.

    Returns the list of working-sheet rows on the PO after the
    operation (newly cloned + pre-existing).
    """
    existing = list_lines(db, po)
    if existing:
        return existing

    source_lines = (
        db.query(QuotDetails)
        .filter(
            QuotDetails.quotId == quotation.quotId,
            QuotDetails.isActive == True,  # noqa: E712
        )
        .order_by(QuotDetails.quotDtlId.asc())
        .all()
    )

    clones: List[QuotPOWorkingSheet] = []
    for src in source_lines:
        row = QuotPOWorkingSheet(
            companyId=po.companyId,
            quotPOId=po.quotPOId,
            # Phase 1A made ``quotOrderCycleId`` NOT NULL on this table.
            # Copy from the owning PO so the cycle-aware /convert path
            # (which always sets the cycle FK on the PO) keeps the
            # constraint satisfied without an extra arg.
            quotOrderCycleId=po.quotOrderCycleId,
            sourceQuotDtlId=src.quotDtlId,
            createdby=user_id,
            **{col: getattr(src, col, None) for col in _CLONE_COLUMNS},
        )
        db.add(row)
        clones.append(row)
    db.flush()
    for row in clones:
        db.refresh(row)
    return clones


def _ensure_editable(po: QuotPurchaseOrder, db: Session | None = None) -> None:
    if po.status not in _LINE_EDITABLE_PO_STATUSES:
        raise WorkingSheetLockedError(
            f"Final Working Sheet is locked because the PO is "
            f"{po.status}. Use Unlock & Edit to amend."
        )
    # 2026-05-21 soft-flow rework: FWS also locks once its cycle has
    # been Approved. Re-generate is the explicit path back to editable.
    # ``db`` is optional for backwards-compat with callers that pre-
    # date the gate; new callers pass it so the cycle's ``fwsStatus``
    # can be checked.
    if db is not None:
        import logging
        log = logging.getLogger(__name__)
        from app.models.quot_order_cycle import QuotOrderCycle
        cycle = (
            db.query(QuotOrderCycle)
            .filter(
                QuotOrderCycle.quotOrderCycleId == po.quotOrderCycleId,
            )
            .first()
        )
        log.info(
            "_ensure_editable po=%s po.cycleId=%s cycle=%s fwsStatus=%s",
            getattr(po, "quotPOId", None),
            getattr(po, "quotOrderCycleId", None),
            cycle.quotOrderCycleId if cycle else None,
            cycle.fwsStatus if cycle else None,
        )
        if cycle is not None and cycle.fwsStatus == "approved":
            raise WorkingSheetLockedError(
                "Final Working Sheet is locked — it was Approved on "
                f"cycle #{cycle.cycleNo}. Click Re-generate FWS to "
                "create a fresh editable draft."
            )


def add_line(
    db: Session,
    po: QuotPurchaseOrder,
    body: QuotPOWorkingSheetLineBody,
    *,
    user_id: int,
) -> QuotPOWorkingSheet:
    _ensure_editable(po, db)
    row = QuotPOWorkingSheet(
        companyId=po.companyId,
        quotPOId=po.quotPOId,
        # ``quotOrderCycleId`` is NOT NULL on the table (Phase 1A
        # migration). Copy from the owning PO so manually-added lines
        # stay within the cycle's working sheet — without this, the
        # INSERT fails with a 23000 NULL violation.
        quotOrderCycleId=po.quotOrderCycleId,
        createdby=user_id,
        **{col: getattr(body, col, None) for col in _CLONE_COLUMNS},
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


def update_line(
    db: Session,
    po: QuotPurchaseOrder,
    line_id: int,
    body: QuotPOWorkingSheetLineBody,
    *,
    user_id: int,
) -> QuotPOWorkingSheet:
    _ensure_editable(po, db)
    row = (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.poWorkingSheetId == line_id,
            QuotPOWorkingSheet.quotPOId == po.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .first()
    )
    if row is None:
        raise WorkingSheetNotFoundError(
            f"Working-sheet line {line_id} not found on this PO."
        )
    for col in _CLONE_COLUMNS:
        new_val = getattr(body, col, None)
        if new_val is not None:
            setattr(row, col, new_val)
    row.lastupdateby = user_id
    db.flush()
    db.refresh(row)
    return row


def delete_line(
    db: Session,
    po: QuotPurchaseOrder,
    line_id: int,
    *,
    user_id: int,
) -> None:
    _ensure_editable(po, db)
    row = (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.poWorkingSheetId == line_id,
            QuotPOWorkingSheet.quotPOId == po.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .first()
    )
    if row is None:
        raise WorkingSheetNotFoundError(
            f"Working-sheet line {line_id} not found on this PO."
        )
    row.isActive = False
    row.lastupdateby = user_id
    db.flush()


def get_line_by_id(
    db: Session,
    po: QuotPurchaseOrder,
    line_id: int,
) -> Optional[QuotPOWorkingSheet]:
    """Helper for endpoints that need to fetch a single line for
    response after a mutation. Returns None if not found / inactive."""
    return (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.poWorkingSheetId == line_id,
            QuotPOWorkingSheet.quotPOId == po.quotPOId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .first()
    )


# ----------------------------------------------------------------------
# LOI / Cycle CR — cycle-scoped helpers (Phase 1B)
# ----------------------------------------------------------------------

def regenerate_fws(
    db: Session,
    cycle,  # QuotOrderCycle (lazy ref to avoid circular import)
    *,
    user_id: int,
    owning_po: QuotPurchaseOrder,
    snapshot=None,  # QuotFWSApprovalSnapshot | None
    re_clone_from_quotation: bool = False,
    parent_cycle=None,  # QuotOrderCycle | None
) -> int:
    """Replace the cycle's active FWS rows with rows from exactly one
    of three sources, mirroring the Viability Re-generate UX:

      * **snapshot** — restore a past FWS approval snapshot (delegates
        to ``approval_snapshot_service.restore_fws_from_snapshot``).
      * **re_clone_from_quotation** — re-clone from the quotation's
        current ``QuotDetails`` rows (the same shape as the initial
        Convert-time clone).
      * **parent_cycle** — clone forward from the parent cycle's live
        FWS rows (same shape as new-cycle inheritance).

    Pass exactly one source. ``owning_po`` is the PO/LOI row the new
    working-sheet rows attribute to (``QuotPOWorkingSheet.quotPOId`` is
    NOT NULL); caller supplies the cycle's formal PO or first LOI.

    Returns the number of new rows inserted.
    """
    from app.core.timezone import now_ist

    sources_set = sum([
        snapshot is not None,
        bool(re_clone_from_quotation),
        parent_cycle is not None,
    ])
    if sources_set != 1:
        raise ValueError(
            "Pick exactly one source for FWS re-generate "
            "(snapshot / quotation / parent_cycle).",
        )

    # Snapshot path — reuse the existing restore helper which already
    # handles deactivate-then-insert from the JSON blob (incl. type
    # coercion for Decimal/date columns) and flips ``fwsStatus`` back
    # to 'draft'.
    if snapshot is not None:
        from app.services.approval_snapshot_service import (
            restore_fws_from_snapshot,
        )
        return restore_fws_from_snapshot(
            db, cycle, snapshot, user_id=user_id,
        )

    # Quotation / parent-cycle paths share the deactivate prelude.
    db.query(QuotPOWorkingSheet).filter(
        QuotPOWorkingSheet.quotOrderCycleId == cycle.quotOrderCycleId,
        QuotPOWorkingSheet.isActive == True,  # noqa: E712
    ).update(
        {
            "isActive": False,
            "lastupdateby": user_id,
            "lastupdateon": now_ist(),
        },
        synchronize_session=False,
    )
    # Re-generate produces a fresh editable draft; the next Approve
    # will lock it again.
    cycle.fwsStatus = "draft"

    if owning_po.quotOrderCycleId != cycle.quotOrderCycleId:
        raise ValueError(
            "owning_po must belong to the cycle being regenerated.",
        )

    inserted = 0
    if re_clone_from_quotation:
        quotation = (
            db.query(QuotSummary)
            .filter(QuotSummary.quotId == cycle.quotId)
            .first()
        )
        if quotation is None:
            raise ValueError("Quotation not found for cycle.")
        source_lines = (
            db.query(QuotDetails)
            .filter(
                QuotDetails.quotId == quotation.quotId,
                QuotDetails.isActive == True,  # noqa: E712
            )
            .order_by(QuotDetails.quotDtlId.asc())
            .all()
        )
        for src in source_lines:
            db.add(QuotPOWorkingSheet(
                companyId=cycle.companyId,
                quotPOId=owning_po.quotPOId,
                quotOrderCycleId=cycle.quotOrderCycleId,
                sourceQuotDtlId=src.quotDtlId,
                createdby=user_id,
                **{col: getattr(src, col, None) for col in _CLONE_COLUMNS},
            ))
            inserted += 1
    else:
        # Parent-cycle path. Pull every active WS row from the parent
        # and attribute the clones to ``owning_po`` in the new cycle.
        parent_rows = list_working_sheet_for_cycle(db, parent_cycle)
        for src in parent_rows:
            db.add(QuotPOWorkingSheet(
                companyId=cycle.companyId,
                quotPOId=owning_po.quotPOId,
                quotOrderCycleId=cycle.quotOrderCycleId,
                sourceQuotDtlId=getattr(src, "sourceQuotDtlId", None),
                createdby=user_id,
                **{col: getattr(src, col, None) for col in _CLONE_COLUMNS},
            ))
            inserted += 1

    db.flush()
    return inserted


def list_working_sheet_for_cycle(
    db: Session, cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
) -> List[QuotPOWorkingSheet]:
    """Return every active FWS line under a cycle, ordered by id for
    deterministic rendering. One Working Sheet per cycle (per CR
    decision C2)."""
    return (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .order_by(QuotPOWorkingSheet.poWorkingSheetId.asc())
        .all()
    )


def clone_working_sheet_for_new_cycle(
    db: Session,
    new_cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
    parent_cycle: "QuotOrderCycle",  # type: ignore[name-defined]  # noqa: F821
    *,
    owning_po: QuotPurchaseOrder,
    user_id: int,
) -> List[QuotPOWorkingSheet]:
    """Seed the new cycle's Working Sheet from the parent cycle's
    inheritance source (approved viability → working sheet fallback).
    Returns the freshly inserted rows.

    Per CR decision C4: rates flow from the parent's last approved
    viability when present, else from its raw working sheet. The
    ``cycle_service.get_inheritance_source`` helper picks the right
    source and hands back the per-line rows; we copy cost-head
    columns 1:1 into the new cycle's WS.

    ``owning_po`` is the PO or LOI the cloned rows attribute to —
    required because ``QuotPOWorkingSheet.quotPOId`` is NOT NULL.
    Callers typically pass the first LOI/PO appended to the new
    cycle. Subsequent LOIs/POs share the same WS rows (one Working
    Sheet per cycle per CR decision C2).

    The clone is a ONE-TIME copy at cycle-start. Subsequent edits to
    the parent don't propagate — that's the snapshot semantics the
    storybook locked.

    Truly-new items added to the new cycle later (LOI brings in a
    dia not in the parent) take a fresh ``RawMaterialCost`` lookup at
    the cycle's start date. That happens in the caller, not here.
    """
    # Deferred import to keep this module free of an import-time
    # dependency on cycle_service (which itself imports FWS rows).
    from app.services.cycle_service import get_inheritance_source

    if owning_po.quotOrderCycleId != new_cycle.quotOrderCycleId:
        raise ValueError(
            "owning_po must belong to new_cycle; got "
            f"po.cycle={owning_po.quotOrderCycleId} vs "
            f"new_cycle={new_cycle.quotOrderCycleId}.",
        )

    src = get_inheritance_source(db, parent_cycle)
    if src.source_type == "none":
        return []

    new_rows: List[QuotPOWorkingSheet] = []
    for src_line in src.lines:
        # Pull cost-head columns directly off the source — works
        # whether the source is QuotViabilityLine or
        # QuotPOWorkingSheet because both mirror QuotDetails.
        payload = {
            col: getattr(src_line, col, None)
            for col in _CLONE_COLUMNS
        }
        row = QuotPOWorkingSheet(
            companyId=new_cycle.companyId,
            quotPOId=owning_po.quotPOId,
            quotOrderCycleId=new_cycle.quotOrderCycleId,
            sourceQuotDtlId=getattr(src_line, "sourceQuotDtlId", None),
            createdby=user_id,
            **payload,
        )
        db.add(row)
        new_rows.append(row)
    db.flush()
    for row in new_rows:
        db.refresh(row)
    return new_rows
