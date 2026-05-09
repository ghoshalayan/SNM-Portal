"""Lifecycle helpers shared across the four stage modules.

The Quotation→Annexure lifecycle has cross-cutting concerns that don't
belong inside any one stage's service file:

* **Unlock-and-Edit audit** — every stage exposes an Unlock-and-Edit
  action (privileged, gated by per-stage ``CanUnlockEdit{Stage}``).
  Each call writes a row to ``LifecycleUnlockAudit`` so admins can
  trace the override after the fact.

* **Stage discriminator constants** — kept here so the four routers
  use the same identifiers and the audit table's ``stage`` column
  stays canonical.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.core.timezone import now_ist
from app.models.lifecycle_unlock_audit import LifecycleUnlockAudit


# Canonical stage identifiers — used both as the audit table's ``stage``
# column value and as the URL segment for the generic unlock endpoint
# (POST /quotations/{id}/{stage}/unlock-edit). Keep these stable;
# changing them breaks the audit log's filterability.
STAGE_QUOTATION = "Quotation"
STAGE_PURCHASE_ORDER = "PurchaseOrder"
STAGE_VIABILITY = "Viability"
STAGE_ANNEXURE = "Annexure"

ALL_STAGES = {
    STAGE_QUOTATION,
    STAGE_PURCHASE_ORDER,
    STAGE_VIABILITY,
    STAGE_ANNEXURE,
}

# Map URL-segment style to canonical stage id. Lets the router accept
# both "purchase-order" and "PurchaseOrder" and resolve to the same
# audit row stage.
_URL_TO_STAGE = {
    "quotation": STAGE_QUOTATION,
    "purchase-order": STAGE_PURCHASE_ORDER,
    "po": STAGE_PURCHASE_ORDER,
    "viability": STAGE_VIABILITY,
    "annexure": STAGE_ANNEXURE,
}

# Per-stage permission flag name on RoleMenuMap. Looked up by
# ``access_service.has_permission`` (which iterates RoleMenuMap.flag).
STAGE_TO_UNLOCK_FLAG = {
    STAGE_QUOTATION: "CanUnlockEditQuotation",
    STAGE_PURCHASE_ORDER: "CanUnlockEditPO",
    STAGE_VIABILITY: "CanUnlockEditViability",
    STAGE_ANNEXURE: "CanUnlockEditAnnexure",
}


def resolve_stage(url_segment: str) -> Optional[str]:
    """Translate a URL slug to the canonical stage id, or None if it
    isn't recognised. Caller turns ``None`` into a 404."""
    if not url_segment:
        return None
    return _URL_TO_STAGE.get(url_segment.lower())


def write_unlock_audit(
    db: Session,
    *,
    company_id: int,
    stage: str,
    entity_id: int,
    user_id: int,
    reason: Optional[str] = None,
) -> LifecycleUnlockAudit:
    """Persist a single Unlock-and-Edit audit row. Caller is
    responsible for the matching permission check (the route layer
    holds the per-stage flag knowledge); this is the side-effect."""
    if stage not in ALL_STAGES:
        raise ValueError(f"Unknown lifecycle stage: {stage!r}")

    row = LifecycleUnlockAudit(
        companyId=company_id,
        stage=stage,
        entityId=entity_id,
        unlockedBy=user_id,
        unlockedOn=now_ist(),
        reason=(reason or None),
        createdby=user_id,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row
