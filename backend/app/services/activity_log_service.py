"""Quotation activity log — append-only audit trail of lifecycle events.

Single entry point: `log_action()`. Called inline from each lifecycle
endpoint so the log is the authoritative 'who did what when'.

Logging is best-effort by design: any DB failure here (e.g. table not
created yet because the migration hasn't been applied, or transient SQL
error) is swallowed so it can never block the underlying business save.
We log the failure to stderr so it's visible in server logs.
"""
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.timezone import now_ist
from app.models.quot_activity_log import QuotActivityLog
from app.models.user import User

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    *,
    quot_id: int,
    company_id: int,
    action: str,
    status: Optional[str],
    user_id: Optional[int],
    outcome: str = "Success",
    details: Optional[str] = None,
    flush: bool = True,
) -> Optional[QuotActivityLog]:
    """Append a log row. Caller is responsible for the enclosing commit.

    Returns the log entry on success, or None if logging failed (in which
    case the caller's transaction is unaffected — we use a SAVEPOINT so a
    failed insert doesn't poison the outer transaction).
    """
    try:
        user_name: Optional[str] = None
        if user_id:
            user = db.query(User.userName).filter(User.userId == user_id).first()
            user_name = user[0] if user else None

        entry = QuotActivityLog(
            quotId=quot_id,
            companyId=company_id,
            action=action,
            status=status,
            outcome=outcome,
            details=details,
            actionOn=now_ist(),
            actionByUserId=user_id,
            actionByName=user_name,
        )

        # SAVEPOINT (nested transaction) so a failure here — e.g. missing
        # table because alembic hasn't been run, or a column-type mismatch —
        # rolls back only this insert, not the parent business operation.
        with db.begin_nested():
            db.add(entry)
            if flush:
                db.flush()
        return entry
    except Exception as exc:
        logger.warning(
            "log_action failed for quotId=%s action=%s: %s",
            quot_id, action, exc,
        )
        return None


def log_failure(
    db: Session,
    *,
    quot_id: int,
    company_id: int,
    action: str,
    user_id: Optional[int],
    exc: Exception,
    status: Optional[str] = None,
) -> None:
    """Helper for except blocks: rolls back the failing transaction, writes
    a Failure log row in a fresh transaction, then commits. Never raises —
    safe to call immediately before re-raising the original exception.
    """
    try:
        db.rollback()
    except Exception:
        pass
    detail = getattr(exc, "detail", None) or str(exc)
    log_action(
        db,
        quot_id=quot_id,
        company_id=company_id,
        action=action,
        status=status,
        user_id=user_id,
        outcome="Failure",
        details=str(detail)[:500],
    )
    try:
        db.commit()
    except Exception:
        pass
