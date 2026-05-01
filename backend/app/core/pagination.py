"""Reusable server-side pagination for list endpoints."""

from typing import Iterable, List, Optional, TypeVar
from pydantic import BaseModel
from fastapi import HTTPException, Query
from sqlalchemy.orm import Query as SAQuery

T = TypeVar("T")

# Raised from 100 → 500 for production scale. List pages use offset pagination
# (for explicit page numbers), so the default stays 25; admins can select 250/500
# for bulk exports. Search-as-you-type dropdowns use cursor_pagination.py instead.
MAX_PAGE_SIZE = 500


class PaginationParams:
    """FastAPI dependency for pagination query parameters."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-based)"),
        pageSize: int = Query(25, ge=1, le=MAX_PAGE_SIZE, description="Items per page"),
        search: Optional[str] = Query(None, description="Search term"),
        sortBy: Optional[str] = Query(None, description="Column to sort by"),
        sortDir: str = Query("asc", regex="^(asc|desc)$", description="Sort direction"),
    ):
        self.page = page
        self.page_size = pageSize
        self.skip = (page - 1) * pageSize
        self.limit = pageSize
        self.search = search.strip() if search else None
        self.sort_by = sortBy
        self.sort_dir = sortDir


class PaginatedResponse(BaseModel):
    """Standard paginated response wrapper."""
    items: List
    total: int
    page: int
    pageSize: int
    totalPages: int


def resolve_sort_column(
    model,
    sort_by: Optional[str],
    *,
    allowed: Iterable[str],
    default: Optional[str] = None,
):
    """Safely resolve `sort_by` to a model column.

    Rejects any name not in `allowed` (returns 400). Defends against column
    injection via `?sortBy=<arbitrary_attr>` — without a whitelist the caller
    can sort by non-column attributes (methods, relationships) which raises
    obscure runtime errors, or in the worst case expose private fields via
    ordering-based side channels.

    Returns the SQLAlchemy column object, or None when no sort is requested
    and `default` is None.
    """
    requested = sort_by or default
    if not requested:
        return None
    allowed_set = set(allowed)
    if requested not in allowed_set:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid sortBy '{requested}'. "
                f"Allowed: {', '.join(sorted(allowed_set))}"
            ),
        )
    col = getattr(model, requested, None)
    if col is None:
        # Column in the whitelist but missing from the model — config bug.
        raise HTTPException(
            status_code=500,
            detail=f"sortBy '{requested}' is whitelisted but missing from model.",
        )
    return col


def paginate(query: SAQuery, params: PaginationParams) -> dict:
    """Apply pagination to a SQLAlchemy query and return paginated result dict.

    Returns a dict matching PaginatedResponse shape.
    """
    total = query.count()
    items = query.offset(params.skip).limit(params.limit).all()
    total_pages = (total + params.page_size - 1) // params.page_size if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": params.page,
        "pageSize": params.page_size,
        "totalPages": total_pages,
    }
