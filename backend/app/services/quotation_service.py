import re

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.quotation import QuotSummary, QuotDetails, QuotTermsNConditions


# Trailing revision suffix used to peel the base number out of an existing
# revised quotation. Anchored at the end so a legitimate "-R" inside the base
# number (e.g. "QUOT-SR-2026-0010") is never mangled.
_REVISION_SUFFIX_RE = re.compile(r"-R\d+$")

# All cost-head column names on QuotDetails — keep in sync with model
COST_HEAD_COLS = [
    "TPWGST", "Marketing", "FreightTrailer", "FreightTruck", "Unloading",
    "OHD", "IFC", "WeighmentDiff", "CD", "SWECharge", "CRS", "IncCharge",
    "ShortLnthCharge", "SpeciFicLnthCharge", "ExtraCharge", "Fluctuation",
    "Commission", "Misc", "Testing", "MOUTOD", "SplDisc", "JC",
]

# All detail columns to copy (item info + cost heads + calculated)
DETAIL_COPY_COLS = [
    "itemid", "itemName", "itemGradeName", "itemDia", "itemLength", "itemUnit", "quantity",
    *COST_HEAD_COLS,
    "modeOfDispatch",
    "basicRate", "totRate", "gstMode", "IGST", "CGST", "SGST", "totAmount",
]


def create_quotation_revision(
    db: Session,
    quot_id: int,
    company_id: int,
    user_id: int,
) -> QuotSummary:
    """Create a new revision of an existing quotation."""
    original = db.query(QuotSummary).filter(
        QuotSummary.quotId == quot_id,
        QuotSummary.isActive == True,
    ).first()

    if not original:
        raise ValueError("Quotation not found")

    # Find the root parent
    parent_id = original.parentQuotId or original.quotId

    # Get max version for this quotation chain
    max_ver = (
        db.query(func.max(QuotSummary.versionNo))
        .filter(
            (QuotSummary.parentQuotId == parent_id) | (QuotSummary.quotId == parent_id),
            QuotSummary.isActive == True,
        )
        .scalar()
    ) or 1

    new_version = max_ver + 1
    base_quot_no = (
        _REVISION_SUFFIX_RE.sub("", original.quotNo) if original.quotNo else "QUOT"
    )
    new_quot_no = f"{base_quot_no}-R{new_version - 1}"

    # Create new quotation summary
    # Lock the previous version — set status to "Revised" so it's non-editable
    original.status = "Revised"

    new_quot = QuotSummary(
        companyId=company_id,
        enqid=original.enqid,
        customerId=original.customerId,
        customerContactId=original.customerContactId,
        siteId=original.siteId,
        quotNo=new_quot_no,
        quotDate=original.quotDate,
        subject=original.subject,
        deliveryTermId=original.deliveryTermId,
        deliveryModeId=original.deliveryModeId,
        refQuotNo=original.refQuotNo,
        remarks=original.remarks,
        # The PO is captured against a specific quotation version; a
        # revision starts fresh — the customer is expected to re-issue
        # a PO against the new version. So we deliberately do NOT copy
        # the original's QuotPurchaseOrder to the revision.
        ownerUserId=original.ownerUserId,
        ownerRoleId=original.ownerRoleId,
        revisionNo=new_version - 1,
        versionNo=new_version,
        parentQuotId=parent_id,
        status="Draft",
        createdby=user_id,
    )
    db.add(new_quot)
    db.flush()

    # Copy details (all columns including cost heads)
    old_details = db.query(QuotDetails).filter(
        QuotDetails.quotId == quot_id,
        QuotDetails.isActive == True,
    ).all()
    for dtl in old_details:
        new_dtl_data = {col: getattr(dtl, col) for col in DETAIL_COPY_COLS}
        new_dtl = QuotDetails(
            companyId=company_id,
            quotId=new_quot.quotId,
            createdby=user_id,
            **new_dtl_data,
        )
        db.add(new_dtl)

    # Copy T&C
    old_tncs = db.query(QuotTermsNConditions).filter(
        QuotTermsNConditions.quotId == quot_id,
        QuotTermsNConditions.isActive == True,
    ).all()
    for tnc in old_tncs:
        new_tnc = QuotTermsNConditions(
            companyId=company_id,
            quotId=new_quot.quotId,
            tncName=tnc.tncName,
            tncDescription=tnc.tncDescription,
            createdby=user_id,
        )
        db.add(new_tnc)

    db.commit()
    db.refresh(new_quot)
    return new_quot
