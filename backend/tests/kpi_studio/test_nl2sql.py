"""NL→SQL tests using a stub LlmProvider.

Covers:
  * /nl/status reflects whether a provider is configured
  * /nl/generate happy path: SQL extracted, validation passes
  * Validator surfaces but doesn't void a usable response when the model
    produces unsafe SQL
  * JSON-fence tolerance (model wraps response in ```json … ```)
  * Empty SQL ("Cannot answer") returns a clean response
  * Missing provider returns 503
  * Schema context builder produces the expected shape
"""
from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

import httpx
from fastapi import FastAPI
from sqlalchemy import (
    Column, Integer, MetaData, String, Table, create_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kpi_studio import KpiStudioConfig, create_router
from kpi_studio.models import KpiBase
from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError, LlmResult,
)
from kpi_studio.services import schema_context
from kpi_studio.services.introspector import reflect_schema


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeUser:
    user_id = 7
    company_id = 42
    is_super_admin = True


@dataclass
class StubProvider(LlmProvider):
    """Replays a canned response. Records last messages for assertions."""
    canned: str
    name: str = "stub"
    last_messages: list = None  # type: ignore[assignment]

    def complete(self, messages, *, json_mode=False, max_tokens=None, temperature=0.2):
        self.last_messages = list(messages)
        return LlmResult(text=self.canned, model="stub-1", latency_ms=12, usage={})


class FailingProvider(LlmProvider):
    name = "failing"

    def complete(self, *args, **kwargs):
        raise LlmProviderError("boom")


def _build_app(provider: LlmProvider | None):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiBase.metadata.create_all(engine)

    md = MetaData()
    Table(
        "customers", md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
        Column("revenue", Integer),
    )
    md.create_all(engine)

    Session = sessionmaker(bind=engine)

    def _auth() -> FakeUser:
        return FakeUser()

    app = FastAPI()
    app.include_router(create_router(KpiStudioConfig(
        auth_dep=_auth,
        metadata_session_factory=Session,
        target_engine=engine,
        tenant_resolver=lambda u: u.company_id,
        permission_checker=lambda u, code: True,
        llm_provider=provider,
    )), prefix="/api/v1/kpi")
    return app, engine


class _ApiBase(unittest.TestCase):
    def _client(self, provider):
        app, _ = _build_app(provider)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )


class StatusEndpointTests(_ApiBase):
    def test_status_disabled_when_no_provider(self):
        async def go():
            async with self._client(None) as c:
                r = await c.get("/api/v1/kpi/nl/status")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json(), {"enabled": False, "provider": None})
        _run(go())

    def test_status_enabled_with_provider(self):
        async def go():
            async with self._client(StubProvider(canned="{}")) as c:
                r = await c.get("/api/v1/kpi/nl/status")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["enabled"], True)
                self.assertEqual(r.json()["provider"], "stub")
        _run(go())


class GenerateEndpointTests(_ApiBase):
    def test_503_when_no_provider(self):
        async def go():
            async with self._client(None) as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={"prompt": "anything", "mode": "single"})
                self.assertEqual(r.status_code, 503)
                self.assertEqual(r.json()["detail"]["error"], "llm_disabled")
        _run(go())

    def test_happy_path(self):
        async def go():
            stub = StubProvider(canned=(
                '{"sql": "SELECT name, revenue FROM customers", '
                '"explanation": "Lists every customer with their revenue."}'
            ))
            async with self._client(stub) as c:
                r = await c.post("/api/v1/kpi/nl/generate",
                                 json={"prompt": "show every customer's revenue", "mode": "single"})
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertIn("SELECT", body["sql"].upper())
                self.assertEqual(body["provider"], "stub")
                self.assertEqual(body["model"], "stub-1")
                self.assertEqual(body["validation"]["ok"], True)
                # The validator injects a LIMIT for sqlite.
                self.assertIn("LIMIT 50000", body["validation"]["rewritten_sql"])
                # Schema context was passed to the model.
                self.assertTrue(any(
                    "customers" in m.content and "revenue" in m.content
                    for m in stub.last_messages if m.role == "system"
                ))
        _run(go())

    def test_unsafe_sql_returns_warning_not_error(self):
        """Validator failure should populate ``validation.message`` but
        still 200 — the user can fix it in the editor."""
        async def go():
            stub = StubProvider(canned=(
                '{"sql": "DROP TABLE customers", "explanation": "..."}'
            ))
            async with self._client(stub) as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={"prompt": "drop everything", "mode": "single"})
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertEqual(body["validation"]["ok"], False)
                self.assertIn("select", (body["validation"]["message"] or "").lower())
        _run(go())

    def test_json_fence_is_tolerated(self):
        async def go():
            stub = StubProvider(canned=(
                'Here is the answer:\n```json\n'
                '{"sql": "SELECT 1", "explanation": "Trivial."}'
                '\n```\nHope that helps.'
            ))
            async with self._client(stub) as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={"prompt": "get one", "mode": "single"})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertIn("SELECT", r.json()["sql"].upper())
        _run(go())

    def test_empty_sql_when_model_declines(self):
        async def go():
            stub = StubProvider(canned=(
                '{"sql": "", "explanation": "Cannot answer — schema lacks an orders table."}'
            ))
            async with self._client(stub) as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={"prompt": "list orders", "mode": "single"})
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["sql"], "")
                self.assertIn("Cannot answer", r.json()["explanation"])
                self.assertEqual(r.json()["validation"]["ok"], False)
        _run(go())

    def test_provider_error_returns_502(self):
        async def go():
            async with self._client(FailingProvider()) as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={"prompt": "anything", "mode": "single"})
                self.assertEqual(r.status_code, 502)
                self.assertEqual(r.json()["detail"]["error"], "llm_error")
        _run(go())


class SchemaContextTests(unittest.TestCase):
    def test_renders_tables_columns_and_fks(self):
        engine = create_engine("sqlite:///:memory:")
        md = MetaData()
        Table(
            "customer", md,
            Column("id", Integer, primary_key=True),
            Column("name", String(50), nullable=False),
        )
        from sqlalchemy import ForeignKey
        Table(
            "orders", md,
            Column("id", Integer, primary_key=True),
            Column("customer_id", Integer, ForeignKey("customer.id"), nullable=False),
            Column("total", Integer),
        )
        md.create_all(engine)

        from kpi_studio.config import KpiStudioConfig
        from sqlalchemy.orm import sessionmaker
        cfg = KpiStudioConfig(
            auth_dep=lambda: None,
            metadata_session_factory=sessionmaker(bind=engine),
            target_engine=engine,
        )
        payload = reflect_schema(engine, cfg)
        text = schema_context.build_schema_context(payload)

        self.assertIn("customer", text)
        self.assertIn("orders", text)
        self.assertIn("[pk]", text)
        # Foreign key arrow.
        self.assertIn("→", text)
        self.assertIn("customer", text.split("→", 1)[1])

    def test_truncates_when_over_max_tables(self):
        engine = create_engine("sqlite:///:memory:")
        md = MetaData()
        for i in range(5):
            Table(f"t{i}", md, Column("id", Integer, primary_key=True))
        md.create_all(engine)

        from kpi_studio.config import KpiStudioConfig
        from sqlalchemy.orm import sessionmaker
        cfg = KpiStudioConfig(
            auth_dep=lambda: None,
            metadata_session_factory=sessionmaker(bind=engine),
            target_engine=engine,
        )
        payload = reflect_schema(engine, cfg)
        text = schema_context.build_schema_context(payload, max_tables=2)
        self.assertIn("additional tables not shown", text)


class ProviderFactoryTests(unittest.TestCase):
    def test_disabled_when_provider_blank(self):
        from kpi_studio.providers.llm import build_provider_from_env
        self.assertIsNone(build_provider_from_env({}))
        self.assertIsNone(build_provider_from_env({"KPI_LLM_PROVIDER": ""}))

    def test_disabled_when_key_missing(self):
        from kpi_studio.providers.llm import build_provider_from_env
        self.assertIsNone(build_provider_from_env({"KPI_LLM_PROVIDER": "openai"}))

    def test_builds_openai_provider(self):
        from kpi_studio.providers.llm import build_provider_from_env, OpenAICompatibleProvider
        p = build_provider_from_env({
            "KPI_LLM_PROVIDER": "openai",
            "KPI_OPENAI_API_KEY": "sk-test",
            "KPI_OPENAI_MODEL": "gpt-4o-mini",
        })
        self.assertIsInstance(p, OpenAICompatibleProvider)
        self.assertEqual(p.name, "openai")  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
