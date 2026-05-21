"""Quotation activity log — append-only audit trail of lifecycle events.

Single entry point: `log_action()`. Called inline from each lifecycle
endpoint so the log is the authoritative 'who did what when'.

Logging is best-effort by design: any DB failure here (e.g. table not
created yet because the migration hasn't been applied, or transient SQL
error) is swallowed so it can never block the underlying business save.
We log the failure to stderr so it's visible in server logs.

**Audit-trail integrity (N17 hardening).**
``log_action`` historically took ``user_id`` as a free positional
parameter — any caller could pass any value, including someone else's
user id, and the log would record it. That makes the trail "the caller
says they were X" rather than "X did this" — useless as evidence.

The fix: pass the authenticated ``ctx: AccessContext`` instead and the
service derives the user id from it. ``ctx`` wins over any
``user_id`` the caller also passes — defense-in-depth against a bug or
intent mismatch. The bare ``user_id`` kwarg is retained as a deprecated
fallback so unmigrated callers keep working; new code should always
pass ``ctx``. Tracker: issues.md item **N17b**.
"""
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.timezone import now_ist
from app.models.quot_activity_log import QuotActivityLog
from app.models.user import User

logger = logging.getLogger(__name__)


def _resolve_user_id(
    ctx: Optional[Any], user_id: Optional[int],
) -> Optional[int]:
    """Pick the authoritative user id for the audit row.

    Order of precedence:
      1. ``ctx.user_id`` — always wins when ctx is provided. Set from
         the JWT, can't be forged by the caller.
      2. ``user_id`` — legacy fallback for callers that haven't been
         migrated yet (issues.md N17b).
      3. ``None`` — system actions / unauthenticated paths.

    Logs a warning when ``ctx`` and ``user_id`` are both provided AND
    disagree — that's a smell worth surfacing during the migration.
    """
    if ctx is not None:
        ctx_uid = getattr(ctx, "user_id", None)
        if user_id is not None and ctx_uid != user_id:
            logger.warning(
                "log_action: caller-supplied user_id=%s ignored in favour of ctx.user_id=%s",
                user_id, ctx_uid,
            )
        return ctx_uid
    return user_id


def log_action(
    db: Session,
    *,
    quot_id: int,
    company_id: int,
    action: str,
    status: Optional[str],
    user_id: Optional[int] = None,
    ctx: Optional[Any] = None,
    outcome: str = "Success",
    details: Optional[str] = None,
    flush: bool = True,
) -> Optional[QuotActivityLog]:
    """Append a log row. Caller is responsible for the enclosing commit.

    Prefer passing ``ctx`` (an ``AccessContext``) — the helper derives
    user identity from the authenticated request, which is the only
    way to keep the audit trail trustworthy. ``user_id`` is retained as
    a deprecated fallback for unmigrated callers.

    Returns the log entry on success, or None if logging failed (in which
    case the caller's transaction is unaffected — we use a SAVEPOINT so a
    failed insert doesn't poison the outer transaction).
    """
    try:
        resolved_uid = _resolve_user_id(ctx, user_id)
        user_name: Optional[str] = None
        if resolved_uid:
            user = db.query(User.userName).filter(User.userId == resolved_uid).first()
            user_name = user[0] if user else None

        entry = QuotActivityLog(
            quotId=quot_id,
            companyId=company_id,
            action=action,
            status=status,
            outcome=outcome,
            details=details,
            actionOn=now_ist(),
            actionByUserId=resolved_uid,
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
    exc: Exception,
    user_id: Optional[int] = None,
    ctx: Optional[Any] = None,
    status: Optional[str] = None,
) -> None:
    """Helper for except blocks: rolls back the failing transaction, writes
    a Failure log row in a fresh transaction, then commits. Never raises —
    safe to call immediately before re-raising the original exception.

    Same ``ctx`` / ``user_id`` precedence as ``log_action``.
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
        ctx=ctx,
        outcome="Failure",
        details=str(detail)[:500],
    )
    try:
        db.commit()
    except Exception:
        pass
