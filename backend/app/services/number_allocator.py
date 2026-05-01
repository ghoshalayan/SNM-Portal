"""Retry helper for serial-number allocation.

`QuotSummary.quotNo` and `CustomerEnquiry.enqNo` are generated as
`<PREFIX>-<userCode>-<fyCode>-<count+1:04d>`. Under concurrent create,
the count-then-insert pattern produces duplicates.

The corresponding filtered unique index (`UX_..._company_<no>`) catches any
duplicate at INSERT time; this helper retries on IntegrityError so the API
caller never sees the conflict — the transaction simply re-allocates and
tries again.

Usage:

    quot = allocate_and_flush(
        db,
        build=lambda qno: build_quotation_with_number(data_dict, qno),
        compute_number=lambda: compute_next_quot_number(db, ctx, fy_code, user_code),
        max_attempts=10,
    )

`build(quotNo)` returns the ORM instance to add (fresh on each attempt —
the rollback invalidates any previously-attached object).
`compute_number()` returns the candidate for this attempt (re-counted each
call so other concurrent inserts are reflected).
"""
from typing import Callable, TypeVar

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

T = TypeVar("T")


def allocate_and_flush(
    db: Session,
    *,
    build: Callable[[str], T],
    compute_number: Callable[[], str],
    max_attempts: int = 10,
    conflict_message: str = "Could not allocate a unique number after retries.",
) -> T:
    """Try to flush an insert with an auto-generated number. Retries on
    IntegrityError (filtered unique index collision) up to max_attempts.

    Caller is responsible for committing after this returns; we only flush
    so side-effect operations can still be appended to the same transaction.
    """
    last_error: IntegrityError | None = None
    for _ in range(max_attempts):
        candidate = compute_number()
        obj = build(candidate)
        db.add(obj)
        try:
            db.flush()
            return obj
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            continue
    # Exhausted retries — surface an explicit error so the client sees a 409
    # rather than a 500 traceback.
    raise HTTPException(status_code=409, detail=conflict_message) from last_error
