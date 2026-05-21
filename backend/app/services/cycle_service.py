"""LOI / Cycle CR service layer — Phase 1B.

Owns the lifecycle of ``QuotOrderCycle`` rows and the rate-inheritance
logic that lets Cycle 2 (and onwards) start from the previous cycle's
last approved viability (or its working sheet as fallback).

Design notes that live with the code:

  * **State machine.** ``Active → Complete | Abandoned``. Once a cycle
    leaves Active it never re-enters; "I clicked close by mistake" is
    resolved by Unlock & Edit (audited) rather than a status flip.
  * **Pure preconditions.** The close-cycle check is split into two
    functions: ``can_close_cycle()`` is pure (takes booleans) and
    ``close_cycle()`` is the DB-touching wrapper. Lets the validation
    logic be unit-tested without a database.
  * **Quotation status side-effect.** Starting Cycle #1 on an
    ``Approved`` quotation flips its status to ``Converted`` and
    stamps ``convertedOn / convertedBy``. Subsequent cycles do not
    re-Convert — the quotation stays Converted once a cycle ever
    existed.
  * **Rate inheritance source.** ``get_inheritance_source()`` resolves
    "where do the new cycle's rates come from?" — locked by the CR's
    decision C4: last *approved* viability under the parent, falling
    back to the parent's working sheet if no approved viability.
    Truly new items (no match in parent) need a fresh
    ``RawMaterialCost`` lookup; that's the caller's job (the helper
    only exposes the source ROWS, not the rate lookup).
"""
from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.timezone import now_ist
from app.models.quot_annexure import QuotAnnexure
from app.models.quot_order_cycle import QuotOrderCycle
from app.models.quot_po_working_sheet import QuotPOWorkingSheet
from app.models.quot_purchase_order import QuotPurchaseOrder
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import QuotSummary

log = get_logger(__name__)


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class CycleValidationError(Exception):
    """Raised when a cycle-level state transition is rejected.

    Endpoints map this to a 400. Distinct from ``ValueError`` so the
    API layer can switch on it instead of pattern-matching strings.
    """


# ----------------------------------------------------------------------
# Pure-function helpers (no DB)
# ----------------------------------------------------------------------

class CloseEligibility(NamedTuple):
    """Result of ``can_close_cycle()``. Boolean ok flag + a list of
    human-readable blockers for the dialog the frontend renders."""
    ok: bool
    blockers: List[str]


def can_close_cycle(
    cycle_status: str,
    has_approved_annexure: bool,
    has_formal_po: bool,
) -> CloseEligibility:
    """Pure precondition check. Caller passes the cycle's status and
    two booleans the DB layer computed (presence of approved annexure
    + presence of at least one non-LOI PO).

    Returns ok=True only when ALL preconditions pass. blockers lists
    every failed check so the frontend can show "fix these N things"
    in one dialog instead of click-then-fail-then-click cycles.
    """
    blockers: List[str] = []
    if cycle_status != "Active":
        blockers.append(
            f"Only Active cycles can be closed (current status: {cycle_status})."
        )
    if not has_approved_annexure:
        blockers.append("No approved annexure on this cycle yet.")
    if not has_formal_po:
        blockers.append(
            "No formal PO has been captured — LOIs alone are not sufficient to close."
        )
    return CloseEligibility(ok=not blockers, blockers=blockers)


def can_abandon_cycle(cycle_status: str) -> CloseEligibility:
    """Pure precondition check for abandonment. Only checks the
    status; abandonment is the escape valve when normal close
    preconditions can't be met (customer cancelled, etc.)."""
    blockers: List[str] = []
    if cycle_status != "Active":
        blockers.append(
            f"Only Active cycles can be abandoned (current status: {cycle_status})."
        )
    return CloseEligibility(ok=not blockers, blockers=blockers)


# ----------------------------------------------------------------------
# Lifecycle operations (DB-touching)
# ----------------------------------------------------------------------

def start_new_cycle(
    db: Session,
    quotation: QuotSummary,
    started_by: int,
    parent_cycle_id: Optional[int] = None,
) -> QuotOrderCycle:
    """Open a new ``QuotOrderCycle`` on the given quotation.

    Cycle #1 is opened on the first ``Convert`` action; subsequent
    cycles (#2, #3, …) come from the explicit "Start New Call-off"
    button (gated by ``CanStartNewCycle``).

    Side effect: if this is Cycle #1 of an Approved quotation, the
    quotation's status flips ``Approved → Converted`` here. That
    matches the legacy single-PO behaviour — the act of opening a
    cycle is the act of converting the quote.
    """
    if quotation.status not in ("Approved", "Converted"):
        raise CycleValidationError(
            f"Cannot start a cycle on quotation in status {quotation.status!r}; "
            "the quotation must be Approved or Converted."
        )

    # Next cycleNo for this quotation — scoped to active rows so a
    # soft-deleted cycle doesn't block re-use of its number (matches
    # the unique-index filter declared on the model).
    max_cycle = (
        db.query(func.max(QuotOrderCycle.cycleNo))
        .filter(
            QuotOrderCycle.quotId == quotation.quotId,
            QuotOrderCycle.isActive == True,  # noqa: E712 — SQL Server BIT
        )
        .scalar()
    ) or 0
    next_cycle_no = max_cycle + 1

    # If caller didn't specify a parent and this isn't Cycle 1, default
    # to the most recent previous cycle. That's the natural lineage
    # for rate inheritance.
    if parent_cycle_id is None and next_cycle_no > 1:
        parent = (
            db.query(QuotOrderCycle)
            .filter(
                QuotOrderCycle.quotId == quotation.quotId,
                QuotOrderCycle.isActive == True,  # noqa: E712
                QuotOrderCycle.cycleNo == next_cycle_no - 1,
            )
            .first()
        )
        if parent is not None:
            parent_cycle_id = parent.quotOrderCycleId

    cycle = QuotOrderCycle(
        companyId=quotation.companyId,
        quotId=quotation.quotId,
        cycleNo=next_cycle_no,
        status="Active",
        parentCycleId=parent_cycle_id,
        startedOn=now_ist(),
        startedBy=started_by,
        createdby=started_by,
    )
    db.add(cycle)
    db.flush()  # Need cycle.quotOrderCycleId before downstream code can FK to it.

    # Cycle #1 on an Approved quotation IS the conversion event.
    # Subsequent cycles don't re-Convert; the quotation stays
    # ``Converted`` once any cycle has ever been opened.
    if next_cycle_no == 1 and quotation.status == "Approved":
        quotation.status = "Converted"
        quotation.convertedOn = now_ist()
        quotation.convertedBy = started_by
        quotation.lastupdateby = started_by
        quotation.lastupdateon = now_ist()

    log.info(
        "cycle_started",
        extra={
            "quotId": quotation.quotId,
            "cycleId": cycle.quotOrderCycleId,
            "cycleNo": next_cycle_no,
            "parentCycleId": parent_cycle_id,
        },
    )
    return cycle


def close_cycle(
    db: Session,
    cycle: QuotOrderCycle,
    user_id: int,
    reason: Optional[str] = None,
) -> QuotOrderCycle:
    """Transition a cycle ``Active → Complete``. Raises ``CycleValidationError``
    when preconditions aren't met — annexure must be approved and at
    least one formal PO captured."""
    has_approved_annexure = _has_approved_annexure(db, cycle.quotOrderCycleId)
    has_formal_po = _has_formal_po(db, cycle.quotOrderCycleId)
    eligibility = can_close_cycle(
        cycle.status, has_approved_annexure, has_formal_po,
    )
    if not eligibility.ok:
        raise CycleValidationError("; ".join(eligibility.blockers))

    cycle.status = "Complete"
    cycle.closedOn = now_ist()
    cycle.closedBy = user_id
    if reason:
        cycle.notes = _append_note(cycle.notes, f"[Close] {reason}")
    cycle.lastupdateby = user_id
    cycle.lastupdateon = now_ist()

    log.info(
        "cycle_closed",
        extra={
            "quotId": cycle.quotId,
            "cycleId": cycle.quotOrderCycleId,
            "cycleNo": cycle.cycleNo,
        },
    )
    return cycle


def abandon_cycle(
    db: Session,
    cycle: QuotOrderCycle,
    user_id: int,
    reason: Optional[str] = None,
) -> QuotOrderCycle:
    """Transition a cycle ``Active → Abandoned``. Used when the
    cycle won't reach Complete (customer cancelled, dispute, etc.).
    No precondition beyond ``status == 'Active'`` — abandonment is
    the explicit relief valve for stuck cycles."""
    eligibility = can_abandon_cycle(cycle.status)
    if not eligibility.ok:
        raise CycleValidationError("; ".join(eligibility.blockers))

    cycle.status = "Abandoned"
    cycle.closedOn = now_ist()
    cycle.closedBy = user_id
    if reason:
        cycle.notes = _append_note(cycle.notes, f"[Abandoned] {reason}")
    cycle.lastupdateby = user_id
    cycle.lastupdateon = now_ist()

    log.info(
        "cycle_abandoned",
        extra={
            "quotId": cycle.quotId,
            "cycleId": cycle.quotOrderCycleId,
            "cycleNo": cycle.cycleNo,
        },
    )
    return cycle


# ----------------------------------------------------------------------
# Rate inheritance
# ----------------------------------------------------------------------

class InheritanceSource(NamedTuple):
    """Result of ``get_inheritance_source()``. ``source_type`` is one
    of 'viability' / 'working_sheet' / 'none'. ``lines`` is the list
    of source rows (empty when source_type == 'none'). The caller
    decides what to do with them — typically clone into the new
    cycle's working sheet, mapping cost-head columns 1:1."""
    source_type: str
    lines: list


def get_inheritance_source(
    db: Session,
    parent_cycle: QuotOrderCycle,
) -> InheritanceSource:
    """Resolve which row collection a new cycle inherits from the
    parent.

    Soft-flow Slice D (2026-05-20 — supersedes the original CR-C4
    rule): new cycles inherit ONLY the parent cycle's latest FWS
    rows. The viability + annexure on the new cycle are regenerated
    from scratch against this inherited FWS (no longer cloned from
    the parent's approved viability).

    Return semantics kept for callers that switch on ``source_type``:
      * ``working_sheet`` — parent had FWS rows; ``lines`` holds them.
      * ``none``          — parent had nothing to clone (legitimate
                            edge case the caller should fail loudly on).
    ``viability`` is no longer returned.
    """
    ws_lines = (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.quotOrderCycleId == parent_cycle.quotOrderCycleId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .all()
    )
    if ws_lines:
        return InheritanceSource(source_type="working_sheet", lines=ws_lines)

    return InheritanceSource(source_type="none", lines=[])


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------

def _has_approved_annexure(db: Session, cycle_id: int) -> bool:
    row = (
        db.query(QuotAnnexure.annexureId)
        .filter(
            QuotAnnexure.quotOrderCycleId == cycle_id,
            QuotAnnexure.isActive == True,  # noqa: E712
            QuotAnnexure.status == "Approved",
        )
        .first()
    )
    return row is not None


def _has_formal_po(db: Session, cycle_id: int) -> bool:
    """True when at least one non-LOI PO has been captured. LOIs alone
    can mature the cycle (Submit & Mature works for either) but the
    close-cycle gate insists on a formal PO existing — otherwise the
    paperwork side is incomplete."""
    row = (
        db.query(QuotPurchaseOrder.quotPOId)
        .filter(
            QuotPurchaseOrder.quotOrderCycleId == cycle_id,
            QuotPurchaseOrder.isActive == True,  # noqa: E712
            QuotPurchaseOrder.isLOI == False,  # noqa: E712
        )
        .first()
    )
    return row is not None


def _append_note(existing: Optional[str], addition: str) -> str:
    """Append a timestamped note to ``cycle.notes`` without losing
    earlier entries. Bounded at 500 chars (the column max) by
    truncating the oldest content."""
    stamped = f"{now_ist().isoformat()} {addition}"
    combined = stamped if not existing else f"{existing}\n{stamped}"
    if len(combined) > 500:
        # Keep the latest 500 chars — losing the oldest entries is the
        # right policy for an audit-style append-only field.
        combined = combined[-500:]
    return combined


def resolve_active_cycle_id(db: Session, quot_id: int) -> Optional[int]:
    """Find the cycle id that downstream artifacts (viability / annexure)
    should attach to on the legacy ``POST /quotations/{id}/viability``
    and ``/annexure`` endpoints. Those endpoints don't take a cycle id
    in their URL, but Phase 1A made ``quotOrderCycleId`` NOT NULL on
    the downstream tables — so we need to derive it.

    Preference order:
      1. The single Active cycle for the quotation (the canonical
         current call-off).
      2. The most-recently-started cycle by ``cycleNo`` (fallback for
         quotations whose cycle just closed but the user is still
         finishing the downstream artifacts).
      3. ``None`` when the quotation has never opened a cycle — caller
         decides what to do (legacy single-PO quotations).
    """
    active = (
        db.query(QuotOrderCycle)
        .filter(
            QuotOrderCycle.quotId == quot_id,
            QuotOrderCycle.isActive == True,  # noqa: E712 — SQL Server BIT
            QuotOrderCycle.status == "Active",
        )
        .order_by(QuotOrderCycle.cycleNo.desc())
        .first()
    )
    if active is not None:
        return active.quotOrderCycleId

    latest = (
        db.query(QuotOrderCycle)
        .filter(
            QuotOrderCycle.quotId == quot_id,
            QuotOrderCycle.isActive == True,  # noqa: E712
        )
        .order_by(QuotOrderCycle.cycleNo.desc())
        .first()
    )
    return latest.quotOrderCycleId if latest else None


__all__ = [
    "CycleValidationError",
    "CloseEligibility",
    "InheritanceSource",
    "can_close_cycle",
    "can_abandon_cycle",
    "start_new_cycle",
    "close_cycle",
    "abandon_cycle",
    "get_inheritance_source",
    "resolve_active_cycle_id",
]
