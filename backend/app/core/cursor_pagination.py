"""Cursor-based pagination for search endpoints.

Offset pagination (`?page=5&pageSize=25`) is fine for list tables where
users jump to specific pages. But for search-as-you-type dropdowns, cursor
pagination is superior:

- O(1) query regardless of result position (WHERE id > N uses index)
- Stable under concurrent inserts (no duplicates/skips)
- Naturally supports "infinite scroll" pattern

Cursor format: base64-encoded JSON of the last row's primary-key value.
Stateless — nothing stored server-side.

Example:
    GET /customers/search?q=acme&limit=50
    → {"items": [...], "nextCursor": "eyJpZCI6NTB9", "hasMore": true}

    GET /customers/search?q=acme&after=eyJpZCI6NTB9&limit=50
    → next batch of 50
"""

import base64
import json
from typing import List, Optional, Tuple

from fastapi import Query
from pydantic import BaseModel
from sqlalchemy.orm import Query as SAQuery


MAX_CURSOR_LIMIT = 200  # hard ceiling — protects backend from huge requests
DEFAULT_CURSOR_LIMIT = 50


class CursorParams:
    """FastAPI dependency for cursor pagination query parameters."""

    def __init__(
        self,
        q: Optional[str] = Query(None, description="Search term (prefix match)"),
        after: Optional[str] = Query(None, description="Opaque cursor from previous response"),
        limit: int = Query(DEFAULT_CURSOR_LIMIT, ge=1, le=MAX_CURSOR_LIMIT),
        ids: Optional[str] = Query(None, description="Comma-separated IDs to look up (for resolving id→label)"),
    ):
        self.q = q.strip() if q else None
        self.after = after
        self.limit = limit
        # Parse ids into list[int] for lookup mode
        self.ids: Optional[List[int]] = None
        if ids:
            try:
                self.ids = [int(x) for x in ids.split(",") if x.strip()]
            except ValueError:
                self.ids = None


class CursorResponse(BaseModel):
    items: List
    nextCursor: Optional[str] = None
    hasMore: bool = False


def encode_cursor(last_id: int) -> str:
    payload = json.dumps({"id": int(last_id)}).encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: Optional[str]) -> Optional[int]:
    if not cursor:
        return None
    try:
        # Re-pad base64 (we stripped `=` during encode)
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding)
        obj = json.loads(raw.decode("ascii"))
        val = obj.get("id")
        return int(val) if val is not None else None
    except Exception:
        # Malformed cursor — ignore, treat as "start from beginning"
        return None


def cursor_paginate(
    query: SAQuery,
    id_col,
    params: CursorParams,
    descending: bool = False,
) -> Tuple[list, Optional[str], bool]:
    """Apply cursor pagination to a SQLAlchemy query.

    Args:
        query: the base query (already filtered by company/permissions)
        id_col: the primary-key column used for ordering (e.g. CustomerMaster.customerId)
        params: CursorParams from FastAPI dependency
        descending: if True, order by id_col DESC and use `id < cursor`
                   (useful for "latest first" search results)

    Returns:
        (items, next_cursor_or_none, has_more)
    """
    cursor_id = decode_cursor(params.after)

    if cursor_id is not None:
        if descending:
            query = query.filter(id_col < cursor_id)
        else:
            query = query.filter(id_col > cursor_id)

    query = query.order_by(id_col.desc() if descending else id_col.asc())
    # Fetch limit+1 to detect if a next page exists
    rows = query.limit(params.limit + 1).all()

    has_more = len(rows) > params.limit
    rows = rows[: params.limit]

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        # Always look up by id_col.key — `last[0]` is the FIRST SELECTED column,
        # not the id column. That's only accidentally correct when callers put
        # the id first; re-ordering the query silently broke the cursor.
        # getattr works on both ORM instances and SQLAlchemy Row tuples.
        try:
            last_id = getattr(last, id_col.key)
        except AttributeError:
            # Mapping-shaped result (e.g. legacy .mappings().all())
            last_id = last[id_col.key] if hasattr(last, "__getitem__") else None
        if last_id is not None:
            next_cursor = encode_cursor(last_id)

    return rows, next_cursor, has_more
