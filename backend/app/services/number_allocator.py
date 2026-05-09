"""Serial-number allocation for ``QuotSummary.quotNo`` /
``CustomerEnquiry.enqNo``.

Numbers follow the pattern ``<PREFIX>-<userCode>-<fyCode>-<count+1:04d>``.
The naive count-then-insert pattern races under concurrent create — two
parallel transactions both read the same ``MAX(...)`` and try to INSERT
the same number. The filtered unique index catches the second one with
``IntegrityError``, but the loser then has to rollback the entire enclosing
transaction and retry. Under bursty contention this can exhaust the retry
budget and 409 even valid requests, and it costs the caller all the work
already done in the same transaction.

C2 fix — when ``lock_key`` is supplied we serialize the count+insert with
SQL Server's ``sp_getapplock``. Acquiring the lock blocks until the prior
allocator's transaction commits (or LockTimeout fires). Inside the lock
the count is fresh-and-stable, so the candidate number cannot collide.
The lock auto-releases at transaction end (``@LockOwner='Transaction'``).

The user-supplied-number path keeps the old shape: no lock, ``max_attempts=1``,
and the IntegrityError is allowed to surface as a 409 so the user picks a
different number.

Usage:

    quot = allocate_and_flush(
        db,
        build=_build_quot,
        compute_number=_next_quot_no,
        lock_key=f"NUM:QUOT:{ctx.company_id}:{user_code}:{fy_code}",
    )
"""
from typing import Callable, Optional, TypeVar

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

T = TypeVar("T")

# 5-second wait before we give up on the lock. Allocation+insert finishes in
# tens of ms in practice, so this only fires if a transaction holding the
# lock has stalled — at which point a clean 409 beats waiting indefinitely.
_LOCK_TIMEOUT_MS = 5000


def _acquire_applock(db: Session, lock_key: str) -> None:
    """Take an exclusive SQL Server applock keyed on ``lock_key``.

    The lock is owned by the current transaction and is released when that
    transaction commits or rolls back — callers don't need a finally block.
    Returns normally on grant; raises HTTPException 409 on timeout / failure.
    Return-code semantics are documented under ``sp_getapplock``:
      0  = granted synchronously
      1  = granted after waiting
      <0 = could not be granted (timeout / deadlock / unavailable)
    """
    result = db.execute(
        text(
            "DECLARE @rc INT; "
            "EXEC @rc = sp_getapplock "
            "  @Resource = :res, "
            "  @LockMode = 'Exclusive', "
            "  @LockOwner = 'Transaction', "
            "  @LockTimeout = :timeout; "
            "SELECT @rc;"
        ),
        {"res": lock_key, "timeout": _LOCK_TIMEOUT_MS},
    ).scalar()
    if result is None or result < 0:
        raise HTTPException(
            status_code=409,
            detail="Number allocation is busy — please retry in a moment.",
        )


def allocate_and_flush(
    db: Session,
    *,
    build: Callable[[str], T],
    compute_number: Callable[[], str],
    max_attempts: int = 10,
    lock_key: Optional[str] = None,
    conflict_message: str = "Could not allocate a unique number after retries.",
) -> T:
    """Flush an insert with an auto-generated (or user-supplied) number.

    When ``lock_key`` is provided, allocation is serialized via
    ``sp_getapplock`` on that key — two callers with the same key queue
    instead of racing, which eliminates the duplicate-number window. The
    IntegrityError handler is kept as defense-in-depth: if a duplicate
    *does* slip through (e.g. raw SQL insert outside the API), the caller
    still gets a clean 409 rather than a 500.

    When ``lock_key`` is None (typical for user-supplied numbers), the
    old optimistic-retry behaviour is preserved.

    Caller is responsible for committing after this returns; we only flush
    so side-effect operations can still be appended to the same transaction.
    """
    if lock_key is not None:
        _acquire_applock(db, lock_key)
        candidate = compute_number()
        obj = build(candidate)
        db.add(obj)
        try:
            db.flush()
            return obj
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=conflict_message) from exc

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
