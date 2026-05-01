"""Per-module data purge for SuperAdmin.

Invariants:
  - Tenant scoped: every statement filters by companyId. No cross-tenant blast.
  - Single transaction: partial failures roll back everything.
  - Soft mode: marks isActive=0 on each affected row (reversible by hand).
  - Hard mode: deletes rows in child-first order to respect FKs. Also deletes
    the underlying storage file for every Asset row that references one.
  - Returns per-table counts so the caller can show what happened.
"""
from dataclasses import dataclass, field
from typing import Dict, List

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.timezone import now_ist
from app.models.asset import Asset
from app.models.customer import (
    CustomerContacts,
    CustomerMaster,
    CustomerSite,
)
from app.models.enquiry import (
    CustomerEnqFollowUp,
    CustomerEnquiry,
    CustomerEnquiryCosting,
    CustomerEnquiryDetails,
)
from app.models.quot_activity_log import QuotActivityLog
from app.models.quot_annexure import QuotAnnexure
from app.models.quot_viability import QuotViabilityLine, QuotViabilitySheet
from app.models.quotation import (
    QuotDetails,
    QuotFollowUp,
    QuotSummary,
    QuotTermsNConditions,
)
from app.services.storage_service import storage_service


# ---- Module → list of (table_key, model, parent_scope_fn) ----------------
# parent_scope_fn(company_id) returns the SQLAlchemy filter expression for that
# table. Assets are a special case: scoped by (companyId, enqid IS NOT NULL) or
# (companyId, quotId IS NOT NULL) depending on which module triggered the row.


@dataclass
class PurgeResult:
    mode: str
    companyId: int
    modules: List[str]
    counts: Dict[str, int] = field(default_factory=dict)
    filesDeleted: int = 0
    filesFailed: int = 0


def _soft_delete(
    db: Session,
    model,
    condition,
    *,
    user_id: int,
    result_key: str,
    result: PurgeResult,
) -> None:
    stmt = (
        update(model)
        .where(condition, model.isActive == True)
        .values(isActive=False, lastupdateby=user_id, lastupdateon=now_ist())
    )
    affected = db.execute(stmt).rowcount or 0
    if affected:
        result.counts[result_key] = result.counts.get(result_key, 0) + affected


def _hard_delete(
    db: Session,
    model,
    condition,
    *,
    result_key: str,
    result: PurgeResult,
) -> None:
    affected = (
        db.query(model)
        .filter(condition)
        .delete(synchronize_session=False)
    )
    if affected:
        result.counts[result_key] = result.counts.get(result_key, 0) + affected


def _delete_asset_files(db: Session, condition, *, result: PurgeResult) -> None:
    """Physically delete the underlying storage file for each Asset row the
    condition matches. Tolerates missing files (already gone) but records
    other failures in `result.filesFailed` so the operator sees a summary.
    """
    # Delayed import to avoid cycle with assets.py
    from app.api.v1.assets import _extract_blob_path  # noqa: WPS433

    rows = db.query(Asset.assetId, Asset.fileUrl).filter(condition).all()
    for _aid, file_url in rows:
        if not file_url:
            continue
        path = _extract_blob_path(file_url)
        if not path:
            continue
        try:
            storage_service.delete_file(path)
            result.filesDeleted += 1
        except FileNotFoundError:
            # Already gone — not a failure.
            pass
        except Exception:
            result.filesFailed += 1


# ---- Public entry point --------------------------------------------------


def purge_data(
    db: Session,
    *,
    company_id: int,
    modules: List[str],
    mode: str,                 # "soft" | "hard"
    user_id: int,
) -> PurgeResult:
    """Purge enquiries / quotations / customers (and their descendants) for a
    single tenant. modules = subset of {'enquiries', 'quotations', 'customers'}.

    Customers depend on enquiries / quotations via FK, so in hard mode we
    reject requests to purge customers without the upstream modules selected
    — SQL Server would reject the DELETE anyway, but this raises a clearer
    400 instead of a cryptic FK violation.
    """
    mode = (mode or "soft").lower()
    if mode not in ("soft", "hard"):
        raise ValueError("mode must be 'soft' or 'hard'")

    ALLOWED_MODULES = {"enquiries", "quotations", "customers"}
    mod_set = {m.lower() for m in modules}
    if not mod_set.issubset(ALLOWED_MODULES):
        raise ValueError(f"Unknown module(s): {mod_set - ALLOWED_MODULES}")
    if not mod_set:
        raise ValueError("Pick at least one module to purge.")

    if mode == "hard" and "customers" in mod_set:
        missing = {"enquiries", "quotations"} - mod_set
        if missing:
            raise ValueError(
                "Hard-deleting Customers requires Enquiries and Quotations "
                f"to be selected too (missing: {sorted(missing)}). Customer "
                "rows are FK-referenced by enquiries/quotations."
            )

    result = PurgeResult(mode=mode, companyId=company_id, modules=sorted(mod_set))

    # --------------- Quotations module ------------------------------------
    # Cascade order (children before parents): activity log → annexure →
    # viability line → viability sheet → followups → tnc → details → summary.
    if "quotations" in mod_set:
        # For "soft", child rows are effectively hidden once their parent is
        # flagged, but we flag children too so direct queries to child tables
        # (activity log, etc.) stay consistent.
        if mode == "hard":
            # Physically delete asset files linked to quotations first, while
            # the Asset rows still exist.
            _delete_asset_files(
                db,
                (Asset.companyId == company_id) & (Asset.quotId.isnot(None)),
                result=result,
            )
            _hard_delete(
                db, Asset,
                (Asset.companyId == company_id) & (Asset.quotId.isnot(None)),
                result_key="assets_quot", result=result,
            )
            _hard_delete(db, QuotActivityLog,
                         QuotActivityLog.companyId == company_id,
                         result_key="quotActivityLog", result=result)
            _hard_delete(db, QuotAnnexure,
                         QuotAnnexure.companyId == company_id,
                         result_key="quotAnnexure", result=result)
            _hard_delete(db, QuotViabilityLine,
                         QuotViabilityLine.companyId == company_id,
                         result_key="quotViabilityLine", result=result)
            _hard_delete(db, QuotViabilitySheet,
                         QuotViabilitySheet.companyId == company_id,
                         result_key="quotViabilitySheet", result=result)
            _hard_delete(db, QuotFollowUp,
                         QuotFollowUp.companyId == company_id,
                         result_key="quotFollowUp", result=result)
            _hard_delete(db, QuotTermsNConditions,
                         QuotTermsNConditions.companyId == company_id,
                         result_key="quotTnC", result=result)
            _hard_delete(db, QuotDetails,
                         QuotDetails.companyId == company_id,
                         result_key="quotDetails", result=result)
            _hard_delete(db, QuotSummary,
                         QuotSummary.companyId == company_id,
                         result_key="quotSummary", result=result)
        else:  # soft
            _soft_delete(db, Asset,
                         (Asset.companyId == company_id) & (Asset.quotId.isnot(None)),
                         user_id=user_id, result_key="assets_quot", result=result)
            _soft_delete(db, QuotActivityLog,
                         QuotActivityLog.companyId == company_id,
                         user_id=user_id, result_key="quotActivityLog", result=result)
            _soft_delete(db, QuotAnnexure,
                         QuotAnnexure.companyId == company_id,
                         user_id=user_id, result_key="quotAnnexure", result=result)
            _soft_delete(db, QuotViabilityLine,
                         QuotViabilityLine.companyId == company_id,
                         user_id=user_id, result_key="quotViabilityLine", result=result)
            _soft_delete(db, QuotViabilitySheet,
                         QuotViabilitySheet.companyId == company_id,
                         user_id=user_id, result_key="quotViabilitySheet", result=result)
            _soft_delete(db, QuotFollowUp,
                         QuotFollowUp.companyId == company_id,
                         user_id=user_id, result_key="quotFollowUp", result=result)
            _soft_delete(db, QuotTermsNConditions,
                         QuotTermsNConditions.companyId == company_id,
                         user_id=user_id, result_key="quotTnC", result=result)
            _soft_delete(db, QuotDetails,
                         QuotDetails.companyId == company_id,
                         user_id=user_id, result_key="quotDetails", result=result)
            _soft_delete(db, QuotSummary,
                         QuotSummary.companyId == company_id,
                         user_id=user_id, result_key="quotSummary", result=result)

    # --------------- Enquiries module -------------------------------------
    # followups → costing → details → enquiry + enquiry-linked assets.
    if "enquiries" in mod_set:
        if mode == "hard":
            _delete_asset_files(
                db,
                (Asset.companyId == company_id) & (Asset.enqid.isnot(None)),
                result=result,
            )
            _hard_delete(db, Asset,
                         (Asset.companyId == company_id) & (Asset.enqid.isnot(None)),
                         result_key="assets_enq", result=result)
            _hard_delete(db, CustomerEnqFollowUp,
                         CustomerEnqFollowUp.companyId == company_id,
                         result_key="enqFollowUp", result=result)
            _hard_delete(db, CustomerEnquiryCosting,
                         CustomerEnquiryCosting.companyId == company_id,
                         result_key="enqCosting", result=result)
            _hard_delete(db, CustomerEnquiryDetails,
                         CustomerEnquiryDetails.companyId == company_id,
                         result_key="enqDetails", result=result)
            _hard_delete(db, CustomerEnquiry,
                         CustomerEnquiry.companyId == company_id,
                         result_key="enquiry", result=result)
        else:
            _soft_delete(db, Asset,
                         (Asset.companyId == company_id) & (Asset.enqid.isnot(None)),
                         user_id=user_id, result_key="assets_enq", result=result)
            _soft_delete(db, CustomerEnqFollowUp,
                         CustomerEnqFollowUp.companyId == company_id,
                         user_id=user_id, result_key="enqFollowUp", result=result)
            _soft_delete(db, CustomerEnquiryCosting,
                         CustomerEnquiryCosting.companyId == company_id,
                         user_id=user_id, result_key="enqCosting", result=result)
            _soft_delete(db, CustomerEnquiryDetails,
                         CustomerEnquiryDetails.companyId == company_id,
                         user_id=user_id, result_key="enqDetails", result=result)
            _soft_delete(db, CustomerEnquiry,
                         CustomerEnquiry.companyId == company_id,
                         user_id=user_id, result_key="enquiry", result=result)

    # --------------- Customers module -------------------------------------
    # sites → contacts → customer. Runs LAST so enquiries/quotations (which
    # FK-reference customerId) are already gone by the time we hit the
    # parent rows in hard mode.
    if "customers" in mod_set:
        if mode == "hard":
            _hard_delete(db, CustomerSite,
                         CustomerSite.companyId == company_id,
                         result_key="customerSite", result=result)
            _hard_delete(db, CustomerContacts,
                         CustomerContacts.companyId == company_id,
                         result_key="customerContacts", result=result)
            _hard_delete(db, CustomerMaster,
                         CustomerMaster.companyId == company_id,
                         result_key="customer", result=result)
        else:
            _soft_delete(db, CustomerSite,
                         CustomerSite.companyId == company_id,
                         user_id=user_id, result_key="customerSite", result=result)
            _soft_delete(db, CustomerContacts,
                         CustomerContacts.companyId == company_id,
                         user_id=user_id, result_key="customerContacts", result=result)
            _soft_delete(db, CustomerMaster,
                         CustomerMaster.companyId == company_id,
                         user_id=user_id, result_key="customer", result=result)

    return result
