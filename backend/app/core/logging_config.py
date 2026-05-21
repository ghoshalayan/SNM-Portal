"""Structured logging for the SNM Portal backend (Phase 0).

Replaces ad-hoc ``print`` / ``logging.getLogger`` calls scattered through
the codebase with a single uniform JSON-friendly logger. Designed so:

  * Production: logs land as JSON lines, easy to ship to a log aggregator
    (Application Insights, CloudWatch, ELK, etc.).
  * Development: pretty console output via ``DEBUG=true`` in env.

Phase 0 keeps the surface tiny — ``get_logger(__name__)`` and a request
context binder. Per-request correlation IDs land in a follow-up once the
FastAPI middleware is wired (Phase 0 task tracker item 2).
"""
import logging
import logging.config
import json
import os
import sys
from typing import Any, Dict


_CONFIGURED = False


class _JSONFormatter(logging.Formatter):
    """Minimal JSON formatter. Avoids the python-json-logger dep for now.
    Extra context attached via ``logger.bind(...)`` (LoggerAdapter-style)
    surfaces under a ``context`` key.
    """

    _STANDARD_ATTRS = frozenset(
        logging.LogRecord(
            "", 0, "", 0, None, None, None,
        ).__dict__.keys()
    ) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Anything tucked onto the record via ``extra={}`` lands here.
        context = {
            k: v for k, v in record.__dict__.items()
            if k not in self._STANDARD_ATTRS and not k.startswith("_")
        }
        if context:
            payload["context"] = context
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None, json_output: bool | None = None) -> None:
    """Wire the root logger once. Idempotent — calling twice is a no-op.

    Parameters
    ----------
    level
        Defaults to ``LOG_LEVEL`` env var (``INFO`` when unset).
    json_output
        Defaults to ``json`` when ``DEBUG=false`` (production), else
        plain console output. Override via ``LOG_FORMAT=json|console``.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()

    if json_output is None:
        fmt = os.getenv("LOG_FORMAT")
        if fmt == "json":
            json_output = True
        elif fmt == "console":
            json_output = False
        else:
            # Default: JSON in prod (DEBUG=false), console in dev.
            json_output = (os.getenv("DEBUG", "false").lower() != "true")

    handler = logging.StreamHandler(stream=sys.stdout)
    if json_output:
        handler.setFormatter(_JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)-30s | %(message)s",
            datefmt="%H:%M:%S",
        ))

    root = logging.getLogger()
    root.setLevel(resolved_level)
    # Avoid double handlers if uvicorn already attached one.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)

    # SQLAlchemy and pyodbc are noisy at INFO. Pin them to WARNING unless
    # the caller explicitly raised the floor.
    for noisy in ("sqlalchemy.engine", "sqlalchemy.pool", "pyodbc"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Convenience accessor — ensures ``configure_logging`` has been
    called and returns the named logger.

    Usage:
        from app.core.logging_config import get_logger
        log = get_logger(__name__)
        log.info("Quotation %d converted to cycle %d", quot_id, cycle_id,
                 extra={"quotId": quot_id, "cycleId": cycle_id})
    """
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
