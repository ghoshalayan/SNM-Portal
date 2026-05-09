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
