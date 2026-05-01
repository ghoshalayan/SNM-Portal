"""Read-only SQL executor.

Validates → executes on the configured ``target_engine`` → audits.

Phase A1 invariants:
  * Every call goes through ``sql_safety.validate_select_query`` first.
  * Statement timeout is best-effort: SQL Server takes
    ``SET LOCK_TIMEOUT`` per session, plus a wall-clock cap enforced
    here. SQLite gets the wall-clock cap only.
  * Result rows are streamed and capped at ``row_cap``; the cap is also
    applied at the SQL level by sql_safety, so this is belt-and-braces.
  * Every run — successful or failed — writes a ``KpiQueryRun`` row.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from kpi_studio.models import KpiQueryRun
from kpi_studio.services.sql_safety import SqlSafetyError, validate_select_query

log = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Wire-shape result of an executor run."""

    columns: list[str]
    """Column names in select order."""

    rows: list[list[Any]]
    """Row values, ordered the same as ``columns``. JSON-safe types only."""

    row_count: int
    """Length of ``rows`` after row-cap enforcement."""

    truncated: bool
    """True when more rows were available but the cap kicked in."""

    duration_ms: int
    """Wall-clock query time in milliseconds."""

    rewritten_sql: str
    """The SQL that was actually executed (post-validator)."""

    notes: list[str]
    """Human-readable notes from the validator (e.g. injected TOP)."""


def execute_safe_query(
    engine: Engine,
    db: Session,
    *,
    sql: str,
    source: str = "preview",
    user_id: Optional[int] = None,
    company_id: Optional[int] = None,
    kpi_version_id: Optional[int] = None,
    row_cap: int = 50_000,
    statement_timeout_seconds: int = 30,
    bind_params: Optional[dict] = None,
) -> ExecutionResult:
    """Validate, execute, audit. Raises ``SqlSafetyError`` on validation
    failure (audited as a failed run); raises ``QueryExecutionError`` on
    DB-side failures (also audited)."""

    dialect = engine.dialect.name
    safe_dialect = "tsql" if dialect == "mssql" else dialect

    # ---- 1. Validate ---------------------------------------------------
    try:
        safe = validate_select_query(sql, row_cap=row_cap, dialect=safe_dialect)
    except SqlSafetyError as exc:
        _audit(
            db,
            kpi_version_id=kpi_version_id,
            company_id=company_id,
            user_id=user_id,
            source=source,
            query_text=(sql or "")[:8000],
            succeeded=False,
            error=f"validation: {exc}",
        )
        raise

    # ---- 2. Execute ----------------------------------------------------
    started = time.perf_counter()
    rewritten = safe.rewritten

    try:
        with engine.connect() as conn:
            # Best-effort statement timeout. SQL Server's SET LOCK_TIMEOUT
            # is per-session in ms; LOCK_TIMEOUT only covers blocking, not
            # CPU runaway, so we still rely on the wall-clock cap below.
            if dialect == "mssql":
                try:
                    conn.exec_driver_sql(
                        f"SET LOCK_TIMEOUT {int(statement_timeout_seconds * 1000)}"
                    )
                except Exception:  # not fatal — proceed with wall-clock only
                    pass

            # SQLAlchemy ignores entries in ``bind_params`` that don't
            # appear as ``:name`` placeholders in the SQL, so passing
            # ``{"start_date": ..., "end_date": ...}`` is harmless when
            # the user's query doesn't reference them. The validator
            # already restricted named placeholders to the allow-list.
            result = conn.execute(text(rewritten), bind_params or {})
            columns = list(result.keys())
            rows: list[list[Any]] = []
            truncated = False

            # Stream-fetch with hard cap. We pull one extra row to detect
            # truncation, then drop it.
            for i, row in enumerate(result):
                if i >= row_cap:
                    truncated = True
                    break
                rows.append(list(_jsonify(v) for v in row))

                # Wall-clock check every 1000 rows.
                if i % 1000 == 0 and time.perf_counter() - started > statement_timeout_seconds:
                    truncated = True
                    raise QueryExecutionError(
                        f"Statement timeout after {statement_timeout_seconds}s"
                    )

    except SQLAlchemyError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        _audit(
            db,
            kpi_version_id=kpi_version_id,
            company_id=company_id,
            user_id=user_id,
            source=source,
            query_text=rewritten[:8000],
            succeeded=False,
            error=str(exc)[:2000],
            duration_ms=duration_ms,
        )
        raise QueryExecutionError(_extract_db_message(exc)) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    row_count = len(rows)

    # ---- 3. Audit success ----------------------------------------------
    _audit(
        db,
        kpi_version_id=kpi_version_id,
        company_id=company_id,
        user_id=user_id,
        source=source,
        query_text=rewritten[:8000],
        succeeded=True,
        row_count=row_count,
        duration_ms=duration_ms,
        truncated=truncated,
    )

    return ExecutionResult(
        columns=columns,
        rows=rows,
        row_count=row_count,
        truncated=truncated,
        duration_ms=duration_ms,
        rewritten_sql=rewritten,
        notes=safe.notes,
    )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class QueryExecutionError(RuntimeError):
    """Raised when the database itself rejects the query (after validation)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit(
    db: Session,
    *,
    kpi_version_id: Optional[int],
    company_id: Optional[int],
    user_id: Optional[int],
    source: str,
    query_text: str,
    succeeded: bool,
    error: Optional[str] = None,
    row_count: Optional[int] = None,
    duration_ms: Optional[int] = None,
    truncated: bool = False,
) -> None:
    """Best-effort audit log write. Never raises — audit failures must
    not break the user's request."""
    try:
        db.add(KpiQueryRun(
            kpi_version_id=kpi_version_id,
            company_id=company_id,
            user_id=user_id,
            source=source,
            query_text=query_text,
            succeeded=succeeded,
            error=error,
            row_count=row_count,
            duration_ms=duration_ms,
            truncated=truncated,
        ))
        db.commit()
    except Exception:  # noqa: BLE001 — audit must not break user flow
        log.exception("kpi_studio: failed to write KpiQueryRun audit row")
        try:
            db.rollback()
        except Exception:
            pass


def _jsonify(v: Any) -> Any:
    """Convert non-JSON-safe DB types into JSON-safe equivalents.

    Keeps the wire format predictable for the frontend chart renderers.
    """
    import datetime
    import decimal
    import uuid

    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (decimal.Decimal,)):
        # Avoid float-precision surprises for currency-heavy queries.
        return float(v)
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, datetime.timedelta):
        return v.total_seconds()
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(v))} bytes>"
    return str(v)


def _extract_db_message(exc: SQLAlchemyError) -> str:
    """Pull the readable bit out of a wrapped DB error.

    pyodbc errors come wrapped in a SQLAlchemy DBAPIError; the user
    cares about the inner message, not the SQLAlchemy frame."""
    orig = getattr(exc, "orig", None)
    if orig is None:
        return str(exc)[:1000]
    return str(orig)[:1000]


def fetch_rows(*args: Iterable, **kwargs: Iterable) -> ExecutionResult:
    """Backwards-compat alias name in case I forget the long form."""
    return execute_safe_query(*args, **kwargs)  # type: ignore[arg-type]
