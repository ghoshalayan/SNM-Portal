"""Unit tests for the Phase 0 structured logging module."""
import io
import json
import logging
import pytest

from app.core.logging_config import (
    _JSONFormatter,
    configure_logging,
    get_logger,
)


pytestmark = pytest.mark.unit


class TestJSONFormatter:
    """Output shape contract — anything shipping logs to a SIEM relies on
    these field names being stable."""

    def _format(self, record: logging.LogRecord) -> dict:
        return json.loads(_JSONFormatter().format(record))

    def test_basic_fields_present(self):
        record = logging.LogRecord(
            name="snm.test", level=logging.INFO, pathname="x", lineno=1,
            msg="hello %s", args=("world",), exc_info=None,
        )
        payload = self._format(record)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "snm.test"
        assert payload["msg"] == "hello world"
        assert "ts" in payload

    def test_extra_context_surfaces_under_context_key(self):
        record = logging.LogRecord(
            name="snm.test", level=logging.INFO, pathname="x", lineno=1,
            msg="cycle started", args=(), exc_info=None,
        )
        # Mimic logger.info("...", extra={...})
        record.quotId = 123
        record.cycleId = 4
        payload = self._format(record)
        assert payload["context"] == {"quotId": 123, "cycleId": 4}

    def test_exception_lands_under_exc_key(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="snm.test", level=logging.ERROR, pathname="x", lineno=1,
                msg="oops", args=(), exc_info=sys.exc_info(),
            )
        payload = self._format(record)
        assert "exc" in payload
        assert "ValueError" in payload["exc"]
        assert "boom" in payload["exc"]


class TestGetLogger:
    def test_get_logger_returns_named_logger(self):
        log = get_logger("snm.tests.smoke")
        assert isinstance(log, logging.Logger)
        assert log.name == "snm.tests.smoke"

    def test_configure_logging_is_idempotent(self):
        # Calling configure_logging twice shouldn't add two handlers
        # to the root logger.
        configure_logging()
        before = len(logging.getLogger().handlers)
        configure_logging()
        after = len(logging.getLogger().handlers)
        assert before == after
