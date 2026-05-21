"""Global error boundary for the SNM Portal backend (Phase 0).

Three pieces glued together:

  1. ``RequestIdMiddleware`` — stamps every incoming request with a UUID,
     exposes it via ``request.state.request_id`` and the response header
     ``X-Request-Id``. Lets a user pasting a request-id from a 500 page
     into a support ticket give ops an instant pivot for log search.

  2. ``http_exception_handler`` — catches ``HTTPException`` (the
     happy-path 4xx surface) and renders a uniform JSON body containing
     ``code / message / requestId``. The existing per-endpoint
     ``raise HTTPException(status_code=400, detail="...")`` calls keep
     working unchanged; the response shape just gets standardised.

  3. ``unhandled_exception_handler`` — catches anything that isn't an
     ``HTTPException``. Logs the full traceback structurally with the
     request_id + path/method, then returns 500 with the same uniform
     JSON shape. Crucial: the user gets a request_id they can paste
     into a ticket; the stack trace stays in the logs, not in the
     response body.

Wire-up lives in ``main.py``:

    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
"""
from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging_config import get_logger

log = get_logger(__name__)


_REQUEST_ID_HEADER = "X-Request-Id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamps every request with a UUID for log correlation. Honours a
    caller-provided ``X-Request-Id`` so distributed-tracing tools can
    propagate context end-to-end."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(_REQUEST_ID_HEADER)
        request_id = incoming or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = request_id
        return response


def _request_id(request: Request) -> str:
    """Pull the request_id stamped by ``RequestIdMiddleware``; fall back
    to a fresh UUID if (somehow) we end up handling an exception before
    the middleware ran. Defensive — should never trigger in practice."""
    rid = getattr(request.state, "request_id", None)
    if rid:
        return rid
    rid = str(uuid.uuid4())
    request.state.request_id = rid
    return rid


_HTTP_CODE_NAMES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
}


def _code_from_status(status_code: int) -> str:
    """Map common HTTP status codes to short symbolic codes the frontend
    or external API consumers can branch on. Falls back to ``HTTP_<N>``
    for anything we haven't catalogued yet."""
    return _HTTP_CODE_NAMES.get(status_code, f"HTTP_{status_code}")


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException,
) -> JSONResponse:
    """Render ``HTTPException`` (and Starlette's) as uniform JSON.

    Preserves the original status code and detail. Existing endpoints
    keep raising ``HTTPException(status_code=..., detail="...")`` — only
    the response wrapping changes.
    """
    request_id = _request_id(request)
    payload = {
        "code": _code_from_status(exc.status_code),
        "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        "requestId": request_id,
    }
    # FastAPI's HTTPException can carry headers (e.g. WWW-Authenticate);
    # preserve them so 401 challenges keep working.
    extra_headers = getattr(exc, "headers", None) or {}
    headers = {_REQUEST_ID_HEADER: request_id, **extra_headers}
    return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)


async def unhandled_exception_handler(
    request: Request, exc: Exception,
) -> JSONResponse:
    """Catch-all for genuine bugs (TypeError, KeyError, ORM violations,
    etc.). The user gets a request_id; the stack trace stays in the
    structured log."""
    request_id = _request_id(request)
    log.exception(
        "unhandled_exception",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "exc_type": type(exc).__name__,
        },
    )
    payload = {
        "code": "INTERNAL_ERROR",
        "message": "An unexpected error occurred. Quote this request id when reporting.",
        "requestId": request_id,
    }
    return JSONResponse(
        status_code=500,
        content=payload,
        headers={_REQUEST_ID_HEADER: request_id},
    )


# Re-export the exception classes so callers writing
# ``except FastAPIHTTPException`` don't need to know about the Starlette
# alias dance. Same class, different import paths historically.
__all__ = [
    "RequestIdMiddleware",
    "http_exception_handler",
    "unhandled_exception_handler",
    "FastAPIHTTPException",
    "StarletteHTTPException",
]
