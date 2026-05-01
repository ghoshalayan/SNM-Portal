from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.core.config import settings
from app.core.dependencies import get_db, get_current_user, CurrentUser
from app.core.pagination import PaginationParams, paginate
from app.models.asset import Asset
from app.models.enquiry import CustomerEnquiry
from app.models.quotation import QuotSummary
from app.services.storage_service import storage_service
from app.services.visibility_service import get_visible_user_ids
from app.services.activity_log_service import log_action
from pydantic import BaseModel

router = APIRouter()


ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg",
}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png",
    "image/jpeg",
}

# Per-category overrides. Missing key → falls back to ALLOWED_* above.
CATEGORY_EXTENSIONS = {
    "po_document": {"pdf", "png", "jpg", "jpeg"},
}
CATEGORY_MIME_TYPES = {
    "po_document": {"application/pdf", "image/png", "image/jpeg"},
}
CATEGORY_MAX_SIZE_BYTES = {
    "po_document": 20 * 1024 * 1024,  # 20 MB
}


class AssetResponse(BaseModel):
    assetId: int
    companyId: int
    enqid: Optional[int] = None
    quotId: Optional[int] = None
    assetName: Optional[str] = None
    fileName: str
    fileUrl: str
    fileType: Optional[str] = None
    fileSize: Optional[int] = None
    category: Optional[str] = None
    isActive: bool

    class Config:
        from_attributes = True


def _get_accessible_entity_ids(db: Session, current_user: CurrentUser) -> dict:
    """Get enquiry IDs and quotation IDs the user can access based on ownership visibility."""
    visible = get_visible_user_ids(
        db, current_user.user_id, current_user.company_id,
        current_user.is_super_admin, role_id=current_user.role_id,
    )
    if visible is None:
        return {"all_access": True}

    enq_ids = {r[0] for r in db.query(CustomerEnquiry.enqid).filter(
        CustomerEnquiry.companyId == current_user.company_id,
        CustomerEnquiry.ownerUserId.in_(visible),
        CustomerEnquiry.isActive == True,
    ).all()}

    quot_ids = {r[0] for r in db.query(QuotSummary.quotId).filter(
        QuotSummary.companyId == current_user.company_id,
        QuotSummary.ownerUserId.in_(visible),
        QuotSummary.isActive == True,
    ).all()}

    return {"all_access": False, "enq_ids": enq_ids, "quot_ids": quot_ids}


@router.get("")
def get_assets(
    enqid: Optional[int] = Query(None),
    quotId: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    q = db.query(Asset).filter(
        Asset.companyId == current_user.company_id,
        Asset.isActive == True,
    )
    if enqid:
        q = q.filter(Asset.enqid == enqid)
    if quotId:
        q = q.filter(Asset.quotId == quotId)
    if category:
        # 'general' matches both NULL and literal 'general' so legacy rows don't disappear
        if category == "general":
            q = q.filter(or_(Asset.category == None, Asset.category == "general"))
        else:
            q = q.filter(Asset.category == category)
    if pagination.search:
        q = q.filter(Asset.fileName.ilike(f"%{pagination.search}%"))

    # Apply parent entity visibility
    access = _get_accessible_entity_ids(db, current_user)
    if not access["all_access"]:
        conditions = []
        if access["enq_ids"]:
            conditions.append(Asset.enqid.in_(access["enq_ids"]))
        if access["quot_ids"]:
            conditions.append(Asset.quotId.in_(access["quot_ids"]))
        # Assets not linked to any entity are accessible to all in company
        conditions.append((Asset.enqid == None) & (Asset.quotId == None))
        q = q.filter(or_(*conditions))

    q = q.order_by(Asset.assetId.desc())
    return paginate(q, pagination)


@router.post("/upload", response_model=AssetResponse, status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    assetName: Optional[str] = Form(None),
    enqid: Optional[int] = Form(None),
    quotId: Optional[int] = Form(None),
    category: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    cat = (category or "general").strip().lower()
    allowed_exts = CATEGORY_EXTENSIONS.get(cat, ALLOWED_EXTENSIONS)
    allowed_mimes = CATEGORY_MIME_TYPES.get(cat, ALLOWED_MIME_TYPES)
    max_size = CATEGORY_MAX_SIZE_BYTES.get(cat)

    # Validate file type
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in allowed_exts:
        raise HTTPException(
            400,
            f"File type '.{ext}' is not allowed. Allowed: {', '.join(sorted(allowed_exts))}",
        )
    if file.content_type and file.content_type not in allowed_mimes:
        raise HTTPException(
            400,
            f"MIME type '{file.content_type}' is not allowed.",
        )

    # Validate access to the parent entity
    if enqid or quotId:
        access = _get_accessible_entity_ids(db, current_user)
        if not access["all_access"]:
            if enqid and enqid not in access.get("enq_ids", set()):
                raise HTTPException(403, "You do not have access to this enquiry")
            if quotId and quotId not in access.get("quot_ids", set()):
                raise HTTPException(403, "You do not have access to this quotation")

    file_data = await file.read()

    if max_size is not None and len(file_data) > max_size:
        raise HTTPException(
            400,
            f"File too large: {len(file_data) / (1024*1024):.1f} MB exceeds the "
            f"{max_size // (1024*1024)} MB limit for this upload.",
        )

    result = storage_service.upload_file(
        file_data=file_data,
        original_filename=file.filename,
        content_type=file.content_type,
    )

    asset = Asset(
        companyId=current_user.company_id,
        enqid=enqid,
        quotId=quotId,
        assetName=assetName or None,
        fileName=result["file_name"],
        fileUrl=result["url"],
        fileType=file.content_type,
        fileSize=len(file_data),
        category=cat,
        createdby=current_user.user_id,
    )
    db.add(asset)
    db.flush()
    if quotId:
        quot = db.query(QuotSummary).filter(
            QuotSummary.quotId == quotId,
            QuotSummary.companyId == current_user.company_id,
        ).first()
        log_action(db, quot_id=quotId, company_id=current_user.company_id,
                   action="File uploaded", status=quot.status if quot else None,
                   user_id=current_user.user_id,
                   details=f"category={cat} · {asset.fileName} "
                           f"({(asset.fileSize or 0) // 1024} KB)")
    db.commit()
    db.refresh(asset)
    return asset


def _extract_blob_path(file_url: str) -> str:
    """Derive the storage blob path from the stored fileUrl.

    Examples:
      Azure URL: https://srmbsaci.blob.core.windows.net/srmb-resources/snmportal/abc.pdf
        → blob path: 'snmportal/abc.pdf' (everything AFTER the container name)
      Local URL: /local-files/abc.pdf
        → blob path: 'abc.pdf'
    """
    if not file_url:
        return ""

    # Strip any query string (SAS tokens, etc.)
    url = file_url.split("?")[0]

    # Local storage shape: /local-files/<name>
    if url.startswith("/local-files/"):
        return url[len("/local-files/"):]

    # Azure shape: https://<account>.blob.core.windows.net/<container>/<blob_path...>
    container = settings.AZURE_BLOB_CONTAINER
    if container and f"/{container}/" in url:
        return url.split(f"/{container}/", 1)[1]

    # Fallback: assume directory + filename live after the host
    # e.g. /<container>/<path> if no host given
    if container and url.startswith(f"/{container}/"):
        return url[len(f"/{container}/"):]

    # Last-resort fallback: take everything after the host
    if "://" in url:
        # https://host/seg1/seg2/.../file.ext  →  seg1/seg2/.../file.ext
        return url.split("://", 1)[1].split("/", 1)[1] if "/" in url.split("://", 1)[1] else url
    return url.lstrip("/")


@router.get("/{asset_id}/download")
def download_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Stream the file directly through the backend.

    Returns the file bytes as an attachment. Works uniformly for both
    Azure Blob and local storage (no CORS / SAS URL gymnastics required).
    """
    from fastapi.responses import Response
    import urllib.parse

    asset = db.query(Asset).filter(
        Asset.assetId == asset_id,
        Asset.companyId == current_user.company_id,
        Asset.isActive == True,
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Verify access via parent entity
    if asset.enqid or asset.quotId:
        access = _get_accessible_entity_ids(db, current_user)
        if not access["all_access"]:
            if asset.enqid and asset.enqid not in access.get("enq_ids", set()):
                raise HTTPException(403, "You do not have access to this asset's enquiry")
            if asset.quotId and asset.quotId not in access.get("quot_ids", set()):
                raise HTTPException(403, "You do not have access to this asset's quotation")

    blob_path = _extract_blob_path(asset.fileUrl)
    if not blob_path:
        raise HTTPException(status_code=500, detail="Cannot determine storage path for asset")

    try:
        file_bytes = storage_service.download_file(blob_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found in storage")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage download failed: {str(e)[:200]}")

    # Log the download only for quotation-scoped assets; enquiry / general
    # assets don't have a quotation timeline to show up on.
    if asset.quotId:
        quot = db.query(QuotSummary).filter(
            QuotSummary.quotId == asset.quotId,
            QuotSummary.companyId == asset.companyId,
        ).first()
        log_action(db, quot_id=asset.quotId, company_id=asset.companyId,
                   action="File downloaded",
                   status=quot.status if quot else None,
                   user_id=current_user.user_id,
                   details=f"category={asset.category or 'general'} · {asset.fileName}")
        db.commit()

    # RFC 5987 encoded filename for non-ASCII safety
    safe_filename = (asset.fileName or f"asset-{asset_id}").replace('"', '_')
    quoted = urllib.parse.quote(safe_filename)
    return Response(
        content=file_bytes,
        media_type=asset.fileType or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{quoted}',
            "Access-Control-Expose-Headers": "Content-Disposition",
            "Content-Length": str(len(file_bytes)),
        },
    )


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    asset = db.query(Asset).filter(
        Asset.assetId == asset_id,
        Asset.companyId == current_user.company_id,
        Asset.isActive == True,
    ).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Verify access via parent entity
    if asset.enqid or asset.quotId:
        access = _get_accessible_entity_ids(db, current_user)
        if not access["all_access"]:
            if asset.enqid and asset.enqid not in access.get("enq_ids", set()):
                raise HTTPException(403, "You do not have access to this asset's enquiry")
            if asset.quotId and asset.quotId not in access.get("quot_ids", set()):
                raise HTTPException(403, "You do not have access to this asset's quotation")

    asset.isActive = False
    asset.lastupdateby = current_user.user_id
    if asset.quotId:
        quot = db.query(QuotSummary).filter(
            QuotSummary.quotId == asset.quotId,
            QuotSummary.companyId == asset.companyId,
        ).first()
        log_action(db, quot_id=asset.quotId, company_id=asset.companyId,
                   action="File deleted",
                   status=quot.status if quot else None,
                   user_id=current_user.user_id,
                   details=f"category={asset.category or 'general'} · {asset.fileName}")
    db.commit()
