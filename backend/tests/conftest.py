"""Pytest fixtures shared across the SNM Portal backend test suite.

Phase 0 keeps this minimal — only what unit tests need. DB-backed
fixtures (in-memory sqlite, app TestClient with overridden ``get_db``,
factory-boy model factories) will be layered on as Phase 1 lands.
"""
import os
import sys
from pathlib import Path

# Ensure the ``app`` package is importable when tests run from the
# backend/ working directory.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# Tests must never read or write production secrets. Force a known-safe
# DB connection string so imports of app.core.config don't blow up.
os.environ.setdefault(
    "DB_CONNECTION_STRING",
    "sqlite:///:memory:",  # never actually opened in unit tests
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-do-not-use-in-prod")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:4200")
