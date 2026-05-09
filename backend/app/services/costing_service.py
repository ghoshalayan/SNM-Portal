from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.enquiry import CustomerEnquiryCosting, CustomerEnquiryDetails
from app.models.raw_material_cost import RawMaterialCost


def get_tp_cost_decimal(db: Session, company_id: int, dia: str) -> Decimal | None:
    """Latest TP cost for a dia, returned as Decimal — use this anywhere the
    value enters arithmetic that writes back to a Numeric(18,2) column.

    Going Decimal → float → Decimal compounds binary-precision drift across
    line items (the bug fixed here): a 0.01-paise drift per row × hundreds
    of rows × dozens of quotations is enough to make finance-side
    reconciliation fail. ``RawMaterialCost.tpcost`` is already a
    ``Numeric(18,2)`` column, so SQLAlchemy hands us a Decimal — we just
    have to stop casting it away.
    """
    result = (
        db.query(RawMaterialCost.tpcost)
        .filter(
            RawMaterialCost.companyId == company_id,
            RawMaterialCost.dia == dia,
            RawMaterialCost.isActive == True,
        )
        .order_by(RawMaterialCost.effectedFrom.desc())
        .first()
    )
    return result[0] if result else None


def get_tp_cost_for_dia(db: Session, company_id: int, dia: str) -> float | None:
    """JSON-friendly wrapper for read-only API responses.

    Cast happens at the API boundary only; never use this in calculations
    that persist back to currency columns. Math paths must call
    ``get_tp_cost_decimal`` directly.
    """
    val = get_tp_cost_decimal(db, company_id, dia)
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
