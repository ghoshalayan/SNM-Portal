from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, model_validator


class QuotPurchaseOrderBody(BaseModel):
    """Shared payload for capturing or editing a PO. The repurposed
    ``PUT /quotations/{id}/mature`` endpoint accepts this body to create
    the PO atomically with the status transition; the dedicated
    ``PUT /quotations/{id}/purchase-order`` accepts the same body for
    edits-while-Matured.

    LOI capture (Convert-as-LOI): when ``isLOI = True``, ``poNo`` may be
    blank — the service auto-generates one in the form ``LOI-{quotId}-
    {seq}``. ``poDate`` doubles as the LOI date. ``loiText`` is an
    optional free-text body for the LOI's intent / scope language.
    """
    poNo: Optional[str] = None
    poDate: date
    customerId: int
    customerContactId: Optional[int] = None
    billingSiteId: Optional[int] = None
    billingAddressManual: Optional[str] = None
    consigneeSiteId: Optional[int] = None
    consigneeAddressManual: Optional[str] = None
    remarks: Optional[str] = None
    # LOI-specific (only meaningful when isLOI=True; ignored otherwise).
    isLOI: bool = False
    loiText: Optional[str] = None

    @model_validator(mode="after")
    def _require_po_no_for_formal_po(self):
        """A formal PO MUST carry an externally-supplied poNo — that's
        the customer's reference and the only way to match invoices
        later. LOIs may omit it (server auto-generates). Validates
        post-construction so the field-level Optional doesn't slide
        a missing poNo through for ``isLOI=False``."""
        if not self.isLOI and not (self.poNo and self.poNo.strip()):
            raise ValueError("poNo is required when capturing a formal PO.")
        return self


def _site_label(site: Any) -> Optional[str]:
    """Mirror the frontend's ``getSiteLabel`` so the PO summary card
    can render directly off the API response without a second lookup
    against the customer's site list (which often doesn't include
    ad-hoc rows)."""
    if site is None:
        return None
    code = (getattr(site, "siteAddressCode", None) or "").strip()
    line = (getattr(site, "addressLine", None) or "").strip()
    if code and line:
        return f"{code} — {line}"
    return code or line or None


class QuotPurchaseOrderResponse(BaseModel):
    quotPOId: int
    companyId: int
    quotId: int
    # Per-stage versioning (Phase 1).
    parentPOId: Optional[int] = None
    versionNo: int = 1
    # Stage-2 status: Draft / Submitted / Rejected.
    status: str = "Draft"
    # Phase 3 freshness pointer.
    sourcedFromQuotationVersion: Optional[int] = None
    poNo: str
    poDate: date
    customerId: int
    customerContactId: Optional[int] = None
    billingSiteId: Optional[int] = None
    billingAddressManual: Optional[str] = None
    consigneeSiteId: Optional[int] = None
    consigneeAddressManual: Optional[str] = None
    remarks: Optional[str] = None
    # LOI-specific (Convert-as-LOI). Mirrors the body fields so the
    # frontend can render the LOI text + flag without an extra fetch.
    isLOI: bool = False
    loiText: Optional[str] = None
    isActive: bool
    createdby: Optional[int] = None
    createdon: Optional[datetime] = None
    lastupdateby: Optional[int] = None
    lastupdateon: Optional[datetime] = None

    # Denormalised labels resolved from the eager-loaded relationships.
    # Populated by the ``_attach_labels`` validator below so the
    # frontend's PO summary card can render directly without a follow-up
    # lookup. They're inert when the relationships aren't loaded — the
    # UI simply falls back to the manual-address text in that case.
    customerName: Optional[str] = None
    contactPersonName: Optional[str] = None
    billingSiteAddress: Optional[str] = None
    consigneeSiteAddress: Optional[str] = None

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def _attach_labels(cls, data: Any) -> Any:
        # When Pydantic builds from an ORM instance (``from_attributes``
        # path), ``data`` is the SQLAlchemy ``QuotPurchaseOrder`` row.
        # Read the eager-loaded relationships and stitch denormalised
        # label fields onto a dict that Pydantic then validates.
        if isinstance(data, dict):
            return data
        if not hasattr(data, "__dict__"):
            return data
        cust = getattr(data, "customer", None)
        contact = getattr(data, "contact", None)
        billing = getattr(data, "billing_site", None)
        consignee = getattr(data, "consignee_site", None)
        merged: dict[str, Any] = {
            # Pull the explicit columns from the ORM row…
            **{
                k: getattr(data, k, None) for k in (
                    "quotPOId", "companyId", "quotId",
                    "parentPOId", "versionNo", "status",
                    "sourcedFromQuotationVersion",
                    "poNo", "poDate",
                    "customerId", "customerContactId",
                    "billingSiteId", "billingAddressManual",
                    "consigneeSiteId", "consigneeAddressManual",
                    "remarks", "isLOI", "loiText", "isActive",
                    "createdby", "createdon", "lastupdateby", "lastupdateon",
                )
            },
            # …and graft the resolved labels.
            "customerName": getattr(cust, "customerName", None) if cust else None,
            "contactPersonName": (
                getattr(contact, "contactPersonName", None) if contact else None
            ),
            "billingSiteAddress": _site_label(billing),
            "consigneeSiteAddress": _site_label(consignee),
        }
        return merged


class StageVersionListItem(BaseModel):
    """Uniform shape for a single version of any lifecycle stage
    (PO / Viability / Annexure). The frontend's VersionSelector
    dropdown renders these regardless of which stage they came from."""
    entityId: int
    versionNo: int
    isHead: bool
    status: Optional[str] = None
    parentVersionId: Optional[int] = None
    createdon: Optional[datetime] = None
    createdby: Optional[int] = None
    summary: Optional[str] = None


class UnlockEditBody(BaseModel):
    """Body for ``POST /quotations/{id}/{stage}/unlock-edit``. Reason
    is optional but encouraged — it lands in ``LifecycleUnlockAudit``
    so admins can trace why the privileged escape valve was used."""
    reason: Optional[str] = None


class AdHocSiteCreate(BaseModel):
    """Body for ``POST /customers/{id}/sites/ad-hoc`` — the "save
    permanently" path of the PO manual-address dialog. Field set
    mirrors the regular Customer New Site form so the resulting row
    is indistinguishable from one created via Customer → Sites tab.
    The handler stamps ``isAdHoc=False`` so it shows up in the
    standard site picker without needing ``includeAdHoc=True``."""
    siteAddressCode: Optional[str] = None
    addressLine: str
    state: Optional[str] = None
    dist: Optional[str] = None
    PIN: Optional[str] = None
    contactPerson1: Optional[str] = None
    contactPhone1: Optional[str] = None
    contactEmail1: Optional[str] = None
    isHeadOffice: Optional[bool] = False
