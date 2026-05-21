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


def _ensure_editable(po: QuotPurchaseOrder) -> None:
    if po.status not in _LINE_EDITABLE_PO_STATUSES:
        raise WorkingSheetLockedError(
            f"Final Working Sheet is locked because the PO is "
            f"{po.status}. Use Unlock & Edit to amend."
        )


def add_line(
    db: Session,
    po: QuotPurchaseOrder,
    body: QuotPOWorkingSheetLineBody,
    *,
    user_id: int,
) -> QuotPOWorkingSheet:
    _ensure_editable(po)
    row = QuotPOWorkingSheet(
        companyId=po.companyId,
        quotPOId=po.quotPOId,
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
    _ensure_editable(po)
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
    _ensure_editable(po)
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
