"""Response shapes for approval-snapshot GET endpoints.

The snapshot row stores its body as a JSON blob (``NVARCHAR(MAX)``); this
schema layer deserializes it so the client gets structured fields rather
than a raw string. Two response shapes per parent entity:

* ``*ApprovalSnapshotSummary`` — metadata only (id, version, approver,
  approvedAt). Used by the history-list endpoint so the dropdown can
  render N approvals without loading N JSON blobs.
* ``*ApprovalSnapshotDetail`` — metadata + the parsed JSON body. Used
  by the "view as approved" toggle to render the frozen state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class _SnapshotBase(BaseModel):
    """Common fields across viability + annexure snapshot responses.

    All identifiers serialize as integers; ``approvedAt`` is ISO-8601
    on the wire (Pydantic v2's default datetime serialization).
    """
    model_config = ConfigDict(from_attributes=True)

    snapshotId: int
    versionNo: int
    approvedByUserId: Optional[int] = None
    approvedByName: Optional[str] = None
    approvedAt: datetime


# ---- Viability ----------------------------------------------------------

class ViabilityApprovalSnapshotSummary(_SnapshotBase):
    """Lightweight header row for the history dropdown."""
    viabilityId: int
    quotId: int


class ViabilityApprovalSnapshotDetail(ViabilityApprovalSnapshotSummary):
    """Header + the parsed JSON body. ``snapshot`` carries
    ``{"sheet": {...sheet columns...}, "lines": [{...line columns...}, ...]}``.
    """
    snapshot: Any  # parsed from snapshotData JSON


class ViabilityApprovalSnapshotList(BaseModel):
    """List response for the history endpoint."""
    items: List[ViabilityApprovalSnapshotSummary]


# ---- FWS (Final Working Sheet) -----------------------------------------

class FWSApprovalSnapshotSummary(_SnapshotBase):
    """Lightweight header for the FWS version dropdown. ``label`` is the
    ``C{cycleNo}-V{versionNo}`` display string the FE renders. The FE
    can request it pre-computed so it doesn't have to know the cycle
    number for every snapshot it lists."""
    quotOrderCycleId: int
    quotId: int
    label: str  # ``C{cycleNo}-V{versionNo}``


class FWSApprovalSnapshotDetail(FWSApprovalSnapshotSummary):
    """Header + parsed JSON body. ``snapshot`` carries a list of all
    active FWS line rows at approval time."""
    snapshot: Any
    contentHash: str


class FWSApprovalSnapshotList(BaseModel):
    items: List[FWSApprovalSnapshotSummary]


# ---- Annexure -----------------------------------------------------------

class AnnexureApprovalSnapshotSummary(_SnapshotBase):
    annexureId: int
    quotId: int


class AnnexureApprovalSnapshotDetail(AnnexureApprovalSnapshotSummary):
    """``snapshot`` carries ``{"annexure": {...annexure columns...}}``.
    Annexure has no child rows — ``diawiseBreakup`` is already an
    in-row JSON column that flows through unchanged."""
    snapshot: Any


class AnnexureApprovalSnapshotList(BaseModel):
    items: List[AnnexureApprovalSnapshotSummary]
