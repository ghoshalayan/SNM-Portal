"""Helpers for writing approval-time snapshots.

Used by the viability and annexure approve endpoints under the soft
flow: at the moment the user clicks Approve, freeze the current head
row (plus children, where applicable) into a snapshot table. The head
row itself stays editable; the snapshot is the canonical "what was
signed off" record from then on.

One snapshot row per Approve action. Re-approval after edits appends
a new snapshot — the chain IS the approval history.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, Numeric
from sqlalchemy.orm import Session

from app.core.timezone import now_ist
from app.models.approval_snapshot import (
    QuotAnnexureApprovalSnapshot,
    QuotFWSApprovalSnapshot,
    QuotViabilityApprovalSnapshot,
)
from app.models.quot_annexure import QuotAnnexure
from app.models.quot_order_cycle import QuotOrderCycle
from app.models.quot_po_working_sheet import QuotPOWorkingSheet
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.user import User


def _json_default(value: Any) -> Any:
    """Coerce SQLAlchemy column values that ``json.dumps`` can't handle
    natively. Snapshot rows must round-trip through JSON without losing
    precision, so Decimal goes through ``str(...)`` (preserves the
    exact stored value) rather than ``float`` (would drift)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"snapshot_data: cannot serialize {type(value).__name__}")


def _row_to_dict(row: Any) -> dict:
    """SQLAlchemy ORM row → dict of column values. We rely on the
    mapped column list rather than ``__dict__`` so we don't accidentally
    serialize private SQLAlchemy state or relationships."""
    return {c.key: getattr(row, c.key) for c in row.__table__.columns}


@dataclass
class SnapshotWriteResult:
    """Mirror of ``FWSApproveResult`` for viability + annexure helpers.

    Lets callers tell whether a fresh snapshot row was created (the
    common case) or whether the content was identical to the latest
    snapshot and D3 short-circuited (``created=False``)."""
    snapshot: Any  # one of the three *ApprovalSnapshot rows
    created: bool


def write_viability_snapshot(
    db: Session,
    sheet: QuotViabilitySheet,
    *,
    approver_user_id: int,
) -> SnapshotWriteResult:
    """Freeze the sheet (header + all lines) at the moment of approval,
    with D3 short-circuit.

    Versioning scope (Phase B fix 2026-05-21): snapshot versionNo +
    history are scoped to the **cycle** rather than the individual
    sheet row. Re-generating a viability creates a new sheet row, but
    its approval chain continues from the prior sheet's last version
    — so the user sees V1, V2, V3, … across regenerations within the
    same cycle. Without this, every regenerate restarted the chain at
    V1, which was confusing.

    Pipeline:

    1. Serialize sheet + lines into canonical JSON (sorted keys).
    2. SHA-256 the JSON.
    3. Find the most recent snapshot for any sheet in the same cycle.
       If its ``contentHash`` matches the new one → D3 short-circuit,
       return the existing snapshot with ``created=False``.
    4. Otherwise write a fresh snapshot row, ``versionNo = max + 1``.

    The caller commits as part of the approve transaction.
    """
    lines = (
        db.query(QuotViabilityLine)
        .filter(QuotViabilityLine.viabilityId == sheet.viabilityId)
        .order_by(QuotViabilityLine.viabilityLineId.asc())
        .all()
    )
    payload = {
        "sheet": _row_to_dict(sheet),
        "lines": [_row_to_dict(line) for line in lines],
    }
    serialized = json.dumps(payload, default=_json_default, sort_keys=True)
    new_hash = _content_hash(serialized)

    # Quotation-wide latest lookup (Phase B fix v2 2026-05-21) — the
    # earlier cycle-JOIN scoping excluded sister sheets whose cycleId
    # was NULL, breaking the version counter across Re-generates. The
    # quotation scope guarantees version-chain continuity regardless of
    # whether cycle data is populated on sister rows.
    latest = (
        db.query(QuotViabilityApprovalSnapshot)
        .filter(QuotViabilityApprovalSnapshot.quotId == sheet.quotId)
        .order_by(QuotViabilityApprovalSnapshot.snapshotId.desc())
        .first()
    )

    # D3: hash-equality short-circuit. NULL contentHash on legacy rows
    # (pre-migration e2f3g4h5i6j7) falls through and a fresh snapshot
    # is written — slightly noisier than the strict no-op path, but
    # never wrong.
    if latest is not None and latest.contentHash == new_hash:
        return SnapshotWriteResult(snapshot=latest, created=False)

    next_version = (latest.versionNo + 1) if latest is not None else 1

    approver_name: str | None = None
    if approver_user_id:
        row = (
            db.query(User.userName)
            .filter(User.userId == approver_user_id)
            .first()
        )
        approver_name = row[0] if row else None

    snap = QuotViabilityApprovalSnapshot(
        companyId=sheet.companyId,
        viabilityId=sheet.viabilityId,
        quotId=sheet.quotId,
        versionNo=next_version,
        contentHash=new_hash,
        approvedByUserId=approver_user_id,
        approvedByName=approver_name,
        approvedAt=now_ist(),
        snapshotData=serialized,
        createdby=approver_user_id,
    )
    db.add(snap)
    return SnapshotWriteResult(snapshot=snap, created=True)


def _coerce_snapshot_value(column, value: Any) -> Any:
    """Inverse of ``_json_default`` — reconstruct a column-typed Python
    value from the JSON-deserialized form. Decimal columns came over as
    strings; date/datetime columns came over as ISO strings; everything
    else passes through. Without this restore would push strings into
    Numeric columns and pyodbc would either reject or silently
    truncate depending on driver settings."""
    if value is None:
        return None
    col_type = column.type
    if isinstance(col_type, Numeric):
        return Decimal(str(value))
    if isinstance(col_type, DateTime) and isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(col_type, Date) and isinstance(value, str):
        # Date columns may have datetime ISO strings if SQL Server returned
        # them with a time component; strip to the date part.
        return date.fromisoformat(value[:10])
    return value


@dataclass
class FWSApproveResult:
    """Outcome of an FWS Approve action.

    ``snapshot`` is always populated. ``created`` distinguishes the two
    D3 cases: ``True`` means a new version was created; ``False`` means
    the current state was identical to the latest snapshot and the
    caller should record a re-approval audit event without bumping
    the version counter (issues.md D3 rule).
    """
    snapshot: QuotFWSApprovalSnapshot
    created: bool


def _serialize_fws_state(rows: list[QuotPOWorkingSheet]) -> str:
    """Canonical JSON of the cycle's active FWS rows. Sorted by
    primary key so the same set of rows always produces the same
    string (and therefore the same content hash) regardless of
    SQLAlchemy iteration order. ``sort_keys=True`` makes the
    per-row dict deterministic too."""
    ordered = sorted(rows, key=lambda r: r.poWorkingSheetId)
    payload = [_row_to_dict(r) for r in ordered]
    return json.dumps(payload, default=_json_default, sort_keys=True)


def _content_hash(serialized: str) -> str:
    """SHA-256 of the canonical JSON. 64 hex chars; matches the
    ``contentHash`` column width."""
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def approve_fws(
    db: Session,
    cycle: QuotOrderCycle,
    *,
    approver_user_id: int,
) -> FWSApproveResult:
    """Approve the cycle's Final Working Sheet, applying D3 semantics.

    Reads every active ``QuotPOWorkingSheet`` row for the cycle,
    computes the canonical JSON + SHA-256, and compares to the latest
    snapshot's stored hash:

    * **Hash matches** → no content change since last Approve.
      Returns the existing snapshot with ``created=False``. Caller
      should log a "re-approval (no changes)" audit event.
    * **No previous snapshot, or hash differs** → write a new
      snapshot row with ``versionNo = (max for cycle) + 1``.
      Returns the new row with ``created=True``.

    The caller is responsible for the enclosing commit and the
    activity-log entry. The DB-level unique on
    ``(quotOrderCycleId, versionNo)`` defends against the racing
    increment so two concurrent approves can't produce duplicate
    version numbers — the second one will raise IntegrityError on
    flush, which the endpoint should convert to 409.
    """
    rows = (
        db.query(QuotPOWorkingSheet)
        .filter(
            QuotPOWorkingSheet.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotPOWorkingSheet.isActive == True,  # noqa: E712
        )
        .all()
    )
    if not rows:
        raise ValueError("Cannot approve an empty Final Working Sheet.")

    serialized = _serialize_fws_state(rows)
    new_hash = _content_hash(serialized)

    latest = (
        db.query(QuotFWSApprovalSnapshot)
        .filter(
            QuotFWSApprovalSnapshot.quotOrderCycleId == cycle.quotOrderCycleId,
            QuotFWSApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .order_by(QuotFWSApprovalSnapshot.snapshotId.desc())
        .first()
    )
    if latest is not None and latest.contentHash == new_hash:
        # D3 — content unchanged. Don't grow the version chain with a
        # duplicate row; return the existing latest. Caller logs the
        # re-approval as an audit event.
        return FWSApproveResult(snapshot=latest, created=False)

    next_version = (latest.versionNo + 1) if latest is not None else 1

    approver_name: str | None = None
    if approver_user_id:
        row = (
            db.query(User.userName)
            .filter(User.userId == approver_user_id)
            .first()
        )
        approver_name = row[0] if row else None

    snap = QuotFWSApprovalSnapshot(
        companyId=cycle.companyId,
        quotOrderCycleId=cycle.quotOrderCycleId,
        quotId=cycle.quotId,
        versionNo=next_version,
        contentHash=new_hash,
        approvedByUserId=approver_user_id,
        approvedByName=approver_name,
        approvedAt=now_ist(),
        snapshotData=serialized,
        createdby=approver_user_id,
    )
    db.add(snap)
    db.flush()
    return FWSApproveResult(snapshot=snap, created=True)


def restore_fws_from_snapshot(
    db: Session,
    cycle: QuotOrderCycle,
    snapshot: QuotFWSApprovalSnapshot,
    *,
    user_id: int,
) -> int:
    """Replace the cycle's current active FWS rows with the snapshot's
    data, so the user can edit forward from that point.

    Mechanics:

    1. Soft-delete every currently-active FWS row for the cycle.
    2. Deserialize the snapshot JSON and insert fresh rows — new
       ``poWorkingSheetId``s, audit columns reset to the restorer,
       cycle id preserved.
    3. The restored rows are the new live draft. A subsequent Approve
       creates a new snapshot forked from the restored base (the
       snapshot's content hash will obviously differ from the latest
       *unless* the user restored the latest version without editing,
       in which case D3 kicks in correctly — no duplicate snapshot).

    The caller commits. Returns the number of rows inserted (useful
    for the activity log entry).

    Sanity: snapshot must belong to the same cycle. Caller is
    responsible for that check before calling — the endpoint
    layer already filters by ``quotOrderCycleId`` so we don't double-
    check here.
    """
    # 1) Deactivate current
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

    # 2) Reconstruct from JSON. Strip columns that must NOT be copied
    # (ID + audit fields are owned by this restore action, not the
    # original approver).
    payload = json.loads(snapshot.snapshotData)
    columns_by_name = {c.key: c for c in QuotPOWorkingSheet.__table__.columns}
    EXCLUDED = {
        "poWorkingSheetId",
        "createdon", "createdby", "lastupdateon", "lastupdateby", "isActive",
    }

    inserted = 0
    for row_data in payload:
        kwargs: dict[str, Any] = {}
        for key, raw in row_data.items():
            if key in EXCLUDED:
                continue
            col = columns_by_name.get(key)
            if col is None:
                # Snapshot was written with a column that has since been
                # dropped from the model — skip it rather than crash.
                continue
            kwargs[key] = _coerce_snapshot_value(col, raw)

        kwargs["createdby"] = user_id
        kwargs["isActive"] = True
        db.add(QuotPOWorkingSheet(**kwargs))
        inserted += 1

    db.flush()
    return inserted


def restore_viability_from_snapshot(
    db: Session,
    sheet: QuotViabilitySheet,
    snapshot: QuotViabilityApprovalSnapshot,
    *,
    user_id: int,
) -> int:
    """Replace the viability sheet's current state (header editable
    fields + all line rows) with the snapshot's frozen content. The
    user can then edit forward; the next Approve creates a new
    snapshot version forked from this restored base.

    Mechanics mirror ``restore_fws_from_snapshot`` but operate on two
    tables: the sheet row (one) and its lines (many).

    Excluded from the restore overwrite:

    * Sheet row: ``viabilityId`` (own PK), audit columns, ``isActive``,
      and ``status`` — restoring is *loading the data*, not flipping
      the head row back to Approved. The user re-approves explicitly
      when ready, which is when a new snapshot is written.
    * Line rows: ``viabilityLineId`` (PK), audit columns, ``isActive``.
      ``viabilityId`` is forced to the current sheet's id so the lines
      attach to the live head (defensive — should already match).

    Caller commits. Returns the number of lines inserted (the sheet
    itself is one row, always overwritten in-place).
    """
    payload = json.loads(snapshot.snapshotData)
    sheet_data = payload.get("sheet", {}) or {}
    line_data = payload.get("lines", []) or []

    # ----- 1) Overwrite the sheet row's editable fields ----------------
    sheet_columns = {c.key: c for c in QuotViabilitySheet.__table__.columns}
    SHEET_EXCLUDED = {
        "viabilityId",
        "createdon", "createdby", "lastupdateon", "lastupdateby", "isActive",
        # The current sheet's status reflects what the user wants to do
        # next — don't roll it back to whatever the snapshot was taken
        # under. Approve creates the next snapshot if/when needed.
        "status",
        # Same reasoning for the legacy approval audit columns on the
        # sheet row itself.
        "approvedby", "approvedon",
    }
    for key, raw in sheet_data.items():
        if key in SHEET_EXCLUDED:
            continue
        col = sheet_columns.get(key)
        if col is None:
            continue
        setattr(sheet, key, _coerce_snapshot_value(col, raw))
    sheet.lastupdateby = user_id
    sheet.lastupdateon = now_ist()

    # ----- 2) Replace the lines ---------------------------------------
    db.query(QuotViabilityLine).filter(
        QuotViabilityLine.viabilityId == sheet.viabilityId,
        QuotViabilityLine.isActive == True,  # noqa: E712
    ).update(
        {
            "isActive": False,
            "lastupdateby": user_id,
            "lastupdateon": now_ist(),
        },
        synchronize_session=False,
    )

    line_columns = {c.key: c for c in QuotViabilityLine.__table__.columns}
    LINE_EXCLUDED = {
        "viabilityLineId",
        "createdon", "createdby", "lastupdateon", "lastupdateby", "isActive",
    }
    inserted = 0
    for row_data in line_data:
        kwargs: dict[str, Any] = {}
        for key, raw in row_data.items():
            if key in LINE_EXCLUDED:
                continue
            col = line_columns.get(key)
            if col is None:
                continue
            kwargs[key] = _coerce_snapshot_value(col, raw)
        # Force the FK to the current live sheet — defensive guard in
        # case a future snapshot was somehow taken against a different
        # head id.
        kwargs["viabilityId"] = sheet.viabilityId
        kwargs["createdby"] = user_id
        kwargs["isActive"] = True
        db.add(QuotViabilityLine(**kwargs))
        inserted += 1

    db.flush()
    return inserted


def restore_annexure_from_snapshot(
    db: Session,
    annexure: QuotAnnexure,
    snapshot: QuotAnnexureApprovalSnapshot,
    *,
    user_id: int,
) -> None:
    """Replace the annexure head's editable fields with the snapshot's
    frozen content. Annexure has no child table (``diawiseBreakup`` is
    in-row JSON), so this is a single-row overwrite.

    Excluded: PK, audit columns, ``isActive``, ``status``, and the
    legacy approval audit columns on the row itself — same reasoning
    as the viability restore.
    """
    payload = json.loads(snapshot.snapshotData)
    ann_data = payload.get("annexure", {}) or {}

    columns_by_name = {c.key: c for c in QuotAnnexure.__table__.columns}
    EXCLUDED = {
        "annexureId",
        "createdon", "createdby", "lastupdateon", "lastupdateby", "isActive",
        # Don't roll the head row back to Approved on restore — the
        # user re-approves explicitly when ready.
        "status",
        # Approval-action audit columns reflect who/when of the most
        # recent approval, not the data content. Leave them on the
        # current row so the head stays an honest record.
        "approvedByUserId", "approvedByName", "approvedon",
    }
    for key, raw in ann_data.items():
        if key in EXCLUDED:
            continue
        col = columns_by_name.get(key)
        if col is None:
            continue
        setattr(annexure, key, _coerce_snapshot_value(col, raw))
    annexure.lastupdateby = user_id
    annexure.lastupdateon = now_ist()
    db.flush()


def write_annexure_snapshot(
    db: Session,
    annexure: QuotAnnexure,
    *,
    approver_user_id: int,
) -> SnapshotWriteResult:
    """Freeze the annexure at the moment of approval, with D3
    short-circuit. Annexure has no child table — ``diawiseBreakup`` is
    already in-row JSON — so the canonical form is just the parent
    row's columns serialized."""
    payload = {"annexure": _row_to_dict(annexure)}
    serialized = json.dumps(payload, default=_json_default, sort_keys=True)
    new_hash = _content_hash(serialized)

    latest = (
        db.query(QuotAnnexureApprovalSnapshot)
        .filter(
            QuotAnnexureApprovalSnapshot.annexureId == annexure.annexureId,
            QuotAnnexureApprovalSnapshot.isActive == True,  # noqa: E712
        )
        .order_by(QuotAnnexureApprovalSnapshot.snapshotId.desc())
        .first()
    )
    if latest is not None and latest.contentHash == new_hash:
        return SnapshotWriteResult(snapshot=latest, created=False)

    # Per-Approve versionNo (same fix as viability) — counter on the
    # snapshot table, not the annexure row's ``versionNo``.
    next_version = (latest.versionNo + 1) if latest is not None else 1

    approver_name: str | None = None
    if approver_user_id:
        row = (
            db.query(User.userName)
            .filter(User.userId == approver_user_id)
            .first()
        )
        approver_name = row[0] if row else None

    snap = QuotAnnexureApprovalSnapshot(
        companyId=annexure.companyId,
        annexureId=annexure.annexureId,
        quotId=annexure.quotId,
        versionNo=next_version,
        contentHash=new_hash,
        approvedByUserId=approver_user_id,
        approvedByName=approver_name,
        approvedAt=now_ist(),
        snapshotData=serialized,
        createdby=approver_user_id,
    )
    db.add(snap)
    return SnapshotWriteResult(snapshot=snap, created=True)
