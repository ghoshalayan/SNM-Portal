from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.enquiry import CustomerEnquiryCosting, CustomerEnquiryDetails
from app.models.raw_material_cost import RawMaterialCost
from app.models.raw_material_cost_log import RawMaterialCostLog


def get_tp_cost_decimal(
    db: Session,
    company_id: int,
    dia: str,
    as_of: Optional[Union[date, datetime]] = None,
) -> Decimal | None:
    """Latest TP cost for a dia, returned as Decimal — use this anywhere the
    value enters arithmetic that writes back to a Numeric(18,2) column.

    When ``as_of`` is supplied, returns the rate that was effective on that
    date (the most recent ``effectedFrom <= as_of``). When omitted, returns
    the latest rate regardless of date — original behaviour, used by paths
    that always want "today's" rate.

    Going Decimal → float → Decimal compounds binary-precision drift across
    line items: a 0.01-paise drift per row × hundreds of rows × dozens of
    quotations is enough to make finance-side reconciliation fail.
    ``RawMaterialCost.tpcost`` is already a ``Numeric(18,2)`` column, so
    SQLAlchemy hands us a Decimal — we just have to stop casting it away.
    """
    # ``RawMaterialCost.effectedFrom`` is a DateTime column. When the
    # caller passes a date, SQL Server expands the bare date to
    # midnight, which silently excludes any rate inserted later that
    # same day (e.g. ``2026-05-17 10:30:00`` > ``2026-05-17 00:00:00``).
    # Promote to end-of-day so the filter behaves intuitively for the
    # user — "as of 17-May" should include every rate active on or
    # before 17-May.
    as_of_cutoff = None
    if as_of is not None:
        as_of_cutoff = as_of if isinstance(as_of, datetime) else datetime.combine(
            as_of, datetime.max.time(),
        )

    # Path 1 — master row. Holds the *current* rate per (company, dia).
    # Always the right answer when the as-of date is on or after the
    # current effectedFrom. Tie-break by PK so same-second corrections
    # resolve to the latest insertion deterministically.
    q = db.query(RawMaterialCost.tpcost).filter(
        RawMaterialCost.companyId == company_id,
        RawMaterialCost.dia == dia,
        RawMaterialCost.isActive == True,
    )
    if as_of_cutoff is not None:
        q = q.filter(RawMaterialCost.effectedFrom <= as_of_cutoff)
    result = q.order_by(
        RawMaterialCost.effectedFrom.desc(),
        RawMaterialCost.rawMaterialCostId.desc(),
    ).first()
    if result is not None:
        return result[0]

    # Path 2 — historical log fallback. Reached when the master's
    # current effectedFrom is *after* the picked date.
    #
    # Each log entry's ``(oldCost, oldEffectedFrom)`` captures the
    # state the master held BEFORE that entry was applied. Walking
    # log entries newest-first by ``changedOn`` and returning the
    # ``oldCost`` of the first entry whose ``oldEffectedFrom`` is
    # on or before the picked date gives the most recent pre-
    # correction state that ever claimed a rate was effective on
    # the picked date.
    #
    # This is "Semantic B" — corrections don't erase the historical
    # truth captured by the log. If the master once held
    # ``(46000, effectedFrom=31-03)`` and was later corrected to
    # ``(46000, effectedFrom=17-04)``, the viability picker can
    # still resolve a date like 05-04 to ₹46,000 — the rate that
    # WAS marketed as effective then, even though current data
    # disagrees.
    log_q = db.query(RawMaterialCostLog.oldCost).filter(
        RawMaterialCostLog.companyId == company_id,
        RawMaterialCostLog.dia == dia,
        RawMaterialCostLog.oldCost.isnot(None),
        RawMaterialCostLog.oldEffectedFrom.isnot(None),
    )
    if as_of_cutoff is not None:
        log_q = log_q.filter(RawMaterialCostLog.oldEffectedFrom <= as_of_cutoff)
    log_result = log_q.order_by(
        RawMaterialCostLog.changedOn.desc(),
        RawMaterialCostLog.logId.desc(),
    ).first()
    return log_result[0] if log_result else None


def get_tp_cost_for_dia(
    db: Session,
    company_id: int,
    dia: str,
    as_of: Optional[Union[date, datetime]] = None,
) -> float | None:
    """JSON-friendly wrapper for read-only API responses.

    Cast happens at the API boundary only; never use this in calculations
    that persist back to currency columns. Math paths must call
    ``get_tp_cost_decimal`` directly.
    """
    val = get_tp_cost_decimal(db, company_id, dia, as_of)
    return float(val) if val is not None else None


def create_new_costing_version(
    db: Session,
    enq_id: int,
    company_id: int,
    user_id: int,
) -> list:
    """Duplicate the latest costing version with versionNo + 1."""
    # Find current max version
    max_version = (
        db.query(func.max(CustomerEnquiryCosting.versionNo))
        .filter(
            CustomerEnquiryCosting.enqid == enq_id,
            CustomerEnquiryCosting.isActive == True,
        )
        .scalar()
    ) or 0

    new_version = max_version + 1

    # Get latest version costings
    latest_costings = (
        db.query(CustomerEnquiryCosting)
        .filter(
            CustomerEnquiryCosting.enqid == enq_id,
            CustomerEnquiryCosting.versionNo == max_version,
            CustomerEnquiryCosting.isActive == True,
        )
        .all()
    )

    cost_fields = [
        "TPWGST", "Marketing",
        "FreightTrailer", "FreightTruck", "Unloading", "OHD", "IFC",
        "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge",
        "ShortLnthCharge", "SpeciFicLnthCharge", "ExtraCharge",
        "Fluctuation", "Commission", "Misc", "Testing", "MOUTOD",
        "SplDisc", "JC", "basicRate", "GST", "EXFORPrice",
    ]

    new_costings = []
    for costing in latest_costings:
        kwargs = {f: getattr(costing, f) for f in cost_fields}
        new_costing = CustomerEnquiryCosting(
            companyId=company_id,
            enqid=enq_id,
            enqdtlid=costing.enqdtlid,
            versionNo=new_version,
            **kwargs,
            createdby=user_id,
        )
        db.add(new_costing)
        new_costings.append(new_costing)

    db.commit()
    for c in new_costings:
        db.refresh(c)
    return new_costings
