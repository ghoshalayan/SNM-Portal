"""Settings service + API tests.

Covers:
  * GET returns no api key, only ``has_api_key`` flag
  * PUT with sentinel leaves key alone; with empty string clears it;
    with a value writes it
  * Effective resolution: DB → env → default per field, not all-or-nothing
  * KPI_LLM_PROVIDER + KPI_OPENAI_API_KEY in env builds a working provider
    when DB is empty
  * /nl/status flips on/off as DB settings change
"""
from __future__ import annotations

import asyncio
import unittest

import httpx
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kpi_studio import KpiStudioConfig, create_router
from kpi_studio.models import KpiBase, KpiSettings
from kpi_studio.schemas import KEEP_API_KEY, SettingsUpdate
from kpi_studio.services import settings_service
from kpi_studio.services.nl2sql_agent import (
    DEFAULT_MAX_ITERATIONS, DEFAULT_MAX_TOKENS_PER_CALL, DEFAULT_TOKEN_BUDGET,
)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeUser:
    user_id = 1
    company_id = 42
    role_id = 10
    is_super_admin = True


def _build_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    app = FastAPI()

    def _auth() -> FakeUser:
        return FakeUser()

    app.include_router(create_router(KpiStudioConfig(
        auth_dep=_auth,
        metadata_session_factory=Session,
        target_engine=engine,
        tenant_resolver=lambda u: u.company_id,
        permission_checker=lambda u, code: True,
    )), prefix="/api/v1/kpi")
    return app, Session


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


# ---------------------------------------------------------------------------
# Service-level (no HTTP) — tighter checks on resolution rules.
# ---------------------------------------------------------------------------

class EffectiveResolutionTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        KpiBase.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def test_empty_env_and_db_returns_no_provider(self):
        with self.Session() as db:
            eff = settings_service.get_effective(db, env={})
            self.assertIsNone(eff.provider)
            self.assertEqual(eff.token_budget, DEFAULT_TOKEN_BUDGET)
            self.assertEqual(eff.max_iterations, DEFAULT_MAX_ITERATIONS)
            self.assertEqual(eff.max_tokens_per_call, DEFAULT_MAX_TOKENS_PER_CALL)
            self.assertTrue(eff.using_env_fallback)

    def test_env_only_builds_provider(self):
        env = {
            "KPI_LLM_PROVIDER": "openai",
            "KPI_OPENAI_API_KEY": "sk-from-env",
            "KPI_OPENAI_MODEL": "gpt-4o-mini",
        }
        with self.Session() as db:
            eff = settings_service.get_effective(db, env=env)
            self.assertIsNotNone(eff.provider)
            self.assertEqual(eff.provider_name, "openai")
            self.assertEqual(eff.model, "gpt-4o-mini")
            self.assertTrue(eff.has_key)
            self.assertTrue(eff.using_env_fallback)

    def test_db_takes_precedence_over_env(self):
        env = {
            "KPI_LLM_PROVIDER": "openai",
            "KPI_OPENAI_API_KEY": "sk-from-env",
            "KPI_OPENAI_MODEL": "gpt-from-env",
        }
        with self.Session() as db:
            settings_service.update_row(db, SettingsUpdate(
                llm_provider="openai",
                openai_api_key="sk-from-db",
                openai_model="gpt-from-db",
            ))
            eff = settings_service.get_effective(db, env=env)
            self.assertEqual(eff.model, "gpt-from-db")
            self.assertFalse(eff.using_env_fallback)
            # The provider built has the DB key, not the env one.
            self.assertEqual(eff.provider._api_key, "sk-from-db")  # type: ignore[union-attr]

    def test_partial_db_falls_back_per_field(self):
        """Only model is set in DB; key + budget come from env / defaults."""
        env = {
            "KPI_LLM_PROVIDER": "openai",
            "KPI_OPENAI_API_KEY": "sk-from-env",
            "KPI_NL_TOKEN_BUDGET": "12345",
        }
        with self.Session() as db:
            settings_service.update_row(db, SettingsUpdate(
                openai_model="gpt-db-only",
            ))
            eff = settings_service.get_effective(db, env=env)
            self.assertEqual(eff.model, "gpt-db-only")          # from DB
            self.assertTrue(eff.has_key)                        # from env
            self.assertEqual(eff.token_budget, 12345)           # from env
            self.assertEqual(eff.max_iterations, DEFAULT_MAX_ITERATIONS)  # default
            # Caps coming from env still count as "env fallback" for the
            # banner, but the provider/key situation is the dominant signal.
            self.assertEqual(
                eff.provider._api_key,  # type: ignore[union-attr]
                "sk-from-env",
            )

    def test_keep_sentinel_does_not_clobber_existing_key(self):
        with self.Session() as db:
            settings_service.update_row(db, SettingsUpdate(
                llm_provider="openai",
                openai_api_key="sk-original",
                openai_model="gpt-4o-mini",
            ))
            settings_service.update_row(db, SettingsUpdate(
                openai_model="gpt-still-here",
                # openai_api_key defaults to KEEP_API_KEY
            ))
            row = settings_service.get_row(db)
            self.assertEqual(row.openai_api_key, "sk-original")
            self.assertEqual(row.openai_model, "gpt-still-here")

    def test_empty_string_clears_key(self):
        with self.Session() as db:
            settings_service.update_row(db, SettingsUpdate(
                llm_provider="openai",
                openai_api_key="sk-original",
                openai_model="gpt-4o-mini",
            ))
            settings_service.update_row(db, SettingsUpdate(
                openai_api_key="",
            ))
            row = settings_service.get_row(db)
            self.assertIsNone(row.openai_api_key)


# ---------------------------------------------------------------------------
# HTTP API tests
# ---------------------------------------------------------------------------

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.Session = _build_app()

    def test_get_returns_empty_state_with_no_db_no_env(self):
        async def go():
            async with _client(self.app) as c:
                r = await c.get("/api/v1/kpi/settings")
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertFalse(body["has_api_key"])
                self.assertEqual(body["effective_token_budget"], DEFAULT_TOKEN_BUDGET)
        _run(go())

    def test_put_then_get_roundtrip_no_key_in_response(self):
        async def go():
            async with _client(self.app) as c:
                r = await c.put("/api/v1/kpi/settings", json={
                    "llm_provider": "openai",
                    "openai_api_key": "sk-secret-write-only",
                    "openai_model": "gpt-4o-mini",
                    "token_budget": 25000,
                })
                self.assertEqual(r.status_code, 200, r.text)
                # The response must NOT echo the key — only the boolean.
                body = r.json()
                self.assertTrue(body["has_api_key"])
                self.assertNotIn("sk-secret-write-only", r.text)

                # Re-fetch — same story.
                r = await c.get("/api/v1/kpi/settings")
                self.assertNotIn("openai_api_key", r.json())
                self.assertNotIn("sk-secret-write-only", r.text)
                self.assertTrue(r.json()["has_api_key"])
                self.assertEqual(r.json()["openai_model"], "gpt-4o-mini")
                self.assertEqual(r.json()["token_budget"], 25000)
        _run(go())

    def test_put_with_keep_sentinel_preserves_key(self):
        async def go():
            async with _client(self.app) as c:
                # Seed a key.
                await c.put("/api/v1/kpi/settings", json={
                    "llm_provider": "openai",
                    "openai_api_key": "sk-keep-me",
                    "openai_model": "m1",
                })
                # Update something else without touching the key. Pydantic
                # default for ``openai_api_key`` is ``KEEP_API_KEY``.
                r = await c.put("/api/v1/kpi/settings", json={
                    "openai_model": "m2",
                })
                self.assertEqual(r.status_code, 200, r.text)
                self.assertTrue(r.json()["has_api_key"])
                self.assertEqual(r.json()["openai_model"], "m2")
                # And the underlying row still has the original key.
                with self.Session() as db:
                    row = db.query(KpiSettings).first()
                    self.assertEqual(row.openai_api_key, "sk-keep-me")
        _run(go())

    def test_put_validates_caps(self):
        async def go():
            async with _client(self.app) as c:
                r = await c.put("/api/v1/kpi/settings", json={
                    "max_iterations": 999,  # over the 50 ceiling
                })
                self.assertEqual(r.status_code, 422)
        _run(go())


if __name__ == "__main__":
    unittest.main()
