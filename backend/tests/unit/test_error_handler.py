"""Unit tests for the Phase 0 global error boundary.

End-to-end test via FastAPI TestClient: spin up a tiny throwaway app
that installs the same middleware + handlers production uses, hit it
with routes designed to trigger every error path, assert the wire
shape and request-id propagation.

These tests deliberately don't depend on any application database or
service modules — they exercise only ``app.core.error_handler``.
"""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.error_handler import (
    RequestIdMiddleware,
    StarletteHTTPException,
    http_exception_handler,
    unhandled_exception_handler,
)


pytestmark = pytest.mark.unit


def _make_app() -> FastAPI:
    """Build a minimal app with only the error-boundary stack wired."""
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    @app.get("/raise-http-400")
    def raise_400():
        raise HTTPException(status_code=400, detail="bad input")

    @app.get("/raise-http-404")
    def raise_404():
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/raise-http-with-headers")
    def raise_with_headers():
        raise HTTPException(
            status_code=401,
            detail="auth required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.get("/raise-bare-exception")
    def raise_bare():
        raise RuntimeError("kaboom — should be caught")

    @app.get("/raise-key-error")
    def raise_key_error():
        d: dict = {}
        return d["missing"]

    return app


class TestRequestIdMiddleware:
    def test_response_has_x_request_id_header_for_success(self):
        client = TestClient(_make_app())
        resp = client.get("/ok")
        assert resp.status_code == 200
        assert "X-Request-Id" in resp.headers
        # Default-generated UUID format: 8-4-4-4-12 hex segments.
        rid = resp.headers["X-Request-Id"]
        assert len(rid) == 36 and rid.count("-") == 4

    def test_incoming_request_id_is_honoured(self):
        client = TestClient(_make_app())
        custom = "ext-trace-12345"
        resp = client.get("/ok", headers={"X-Request-Id": custom})
        assert resp.headers["X-Request-Id"] == custom

    def test_request_id_present_on_error_responses_too(self):
        # ``raise_server_exceptions=False`` — otherwise TestClient
        # re-raises 500-class exceptions instead of returning the
        # handler's response, which is exactly what we want to assert
        # on here.
        client = TestClient(_make_app(), raise_server_exceptions=False)
        for path in ("/raise-http-400", "/raise-bare-exception"):
            resp = client.get(path)
            assert "X-Request-Id" in resp.headers, f"missing on {path}"


class TestHttpExceptionShape:
    def test_400_uses_uniform_json_shape(self):
        client = TestClient(_make_app())
        resp = client.get("/raise-http-400")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == "BAD_REQUEST"
        assert body["message"] == "bad input"
        assert body["requestId"] == resp.headers["X-Request-Id"]

    def test_404_maps_to_not_found_code(self):
        client = TestClient(_make_app())
        resp = client.get("/raise-http-404")
        assert resp.status_code == 404
        assert resp.json()["code"] == "NOT_FOUND"

    def test_extra_headers_on_http_exception_are_preserved(self):
        client = TestClient(_make_app())
        resp = client.get("/raise-http-with-headers")
        assert resp.status_code == 401
        # WWW-Authenticate must survive the wrap-and-return-JSON path,
        # otherwise browser auth challenges break.
        assert resp.headers.get("WWW-Authenticate") == "Bearer"
        assert resp.json()["code"] == "UNAUTHENTICATED"

    def test_unknown_status_falls_back_to_http_n_code(self):
        # 418 isn't in our catalogue — should serialize as HTTP_418.
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)
        app.add_exception_handler(StarletteHTTPException, http_exception_handler)

        @app.get("/teapot")
        def teapot():
            raise HTTPException(status_code=418, detail="i'm a teapot")

        client = TestClient(app)
        resp = client.get("/teapot")
        assert resp.status_code == 418
        assert resp.json()["code"] == "HTTP_418"


class TestUnhandledExceptionShape:
    def test_runtime_error_becomes_500_with_request_id(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/raise-bare-exception")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == "INTERNAL_ERROR"
        # Important: the actual exception string is NOT leaked in the
        # response body — it stays in the structured log.
        assert "kaboom" not in body["message"]
        assert body["requestId"] == resp.headers["X-Request-Id"]

    def test_key_error_is_caught_and_returned_as_500(self):
        client = TestClient(_make_app(), raise_server_exceptions=False)
        resp = client.get("/raise-key-error")
        assert resp.status_code == 500
        assert resp.json()["code"] == "INTERNAL_ERROR"
