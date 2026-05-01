"""Slow-query monitor middleware.

Logs a warning when any API request exceeds a configurable threshold.
Also exposes the duration in a response header (X-Response-Time-Ms) so
ops/monitoring can surface regressions.

This is a soft watchdog — it does not kill the request (FastAPI/Starlette
doesn't safely support cancelling an in-flight DB query without risking
pool corruption). The intent is to surface problems *after* they occur so
you can add indexes or optimize queries.

Threshold defaults to 2000ms. Override via env var SLOW_QUERY_THRESHOLD_MS.
"""

import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("snm.slow_query")

DEFAULT_THRESHOLD_MS = int(os.getenv("SLOW_QUERY_THRESHOLD_MS", "2000"))


class SlowQueryMiddleware(BaseHTTPMiddleware):
    """Logs requests that exceed the slow-query threshold."""

    def __init__(self, app, threshold_ms: int = DEFAULT_THRESHOLD_MS):
        super().__init__(app)
        self.threshold_ms = threshold_ms

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        response.headers["X-Response-Time-Ms"] = str(elapsed_ms)

        if elapsed_ms >= self.threshold_ms:
            # Log with enough context to identify the slow endpoint in production
            logger.warning(
                "slow_query threshold=%dms elapsed=%dms method=%s path=%s query=%s",
                self.threshold_ms,
                elapsed_ms,
                request.method,
                request.url.path,
                str(request.url.query)[:200],
            )

        return response
