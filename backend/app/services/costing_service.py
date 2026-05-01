from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.enquiry import CustomerEnquiryCosting, CustomerEnquiryDetails
from app.models.raw_material_cost import RawMaterialCost


def get_tp_cost_for_dia(db: Session, company_id: int, dia: str) -> float | None:
    """Get the latest TP cost for a given dia from RawMaterialCost."""
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
    return float(result[0]) if result else None


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
