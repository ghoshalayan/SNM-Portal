"""End-to-end KPI CRUD tests against in-memory SQLite.

Spin up a FastAPI app + the kpi_studio router, with the same SQLite
engine acting as both metadata DB and target DB. Stateless auth — every
request gets the same fake user.

Verifies the full happy path: create → list → get → update → run → delete.
"""
from __future__ import annotations

import asyncio
import unittest

import httpx
from fastapi import FastAPI
from sqlalchemy import (
    Column, Integer, MetaData, String, Table, create_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _run(coro):
    """Tiny ``asyncio.run`` wrapper so tests stay sync."""
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)

from kpi_studio import KpiStudioConfig, create_router
from kpi_studio.models import KpiBase


class FakeUser:
    user_id = 7
    company_id = 42
    is_super_admin = True


def _build_app():
    # StaticPool keeps every connection on the same in-memory DB; without it
    # SQLite gives each pooled connection its own (empty) database.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiBase.metadata.create_all(engine)

    # Add a sample target table the SQL can hit.
    md = MetaData()
    customers = Table(
        "customers", md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
        Column("region", String(50)),
        Column("revenue", Integer),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(customers.insert(), [
            {"id": 1, "name": "Acme", "region": "North", "revenue": 100},
            {"id": 2, "name": "Beta", "region": "South", "revenue": 200},
            {"id": 3, "name": "Gamma", "region": "North", "revenue": 50},
        ])

    Session = sessionmaker(bind=engine)

    def _fake_auth() -> FakeUser:
        return FakeUser()

    app = FastAPI()
    app.include_router(create_router(KpiStudioConfig(
        auth_dep=_fake_auth,
        metadata_session_factory=Session,
        target_engine=engine,
        tenant_resolver=lambda u: u.company_id,
        permission_checker=lambda u, code: True,
    )), prefix="/api/v1/kpi")
    return app


class KpiCrudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _build_app()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    def test_full_lifecycle(self):
        async def go():
            async with self._client() as client:
                # 1. Preview an unsaved query.
                r = await client.post("/api/v1/kpi/kpis/preview", json={
                    "query_text":
                        "SELECT region, SUM(revenue) AS total FROM customers GROUP BY region",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertEqual(body["row_count"], 2)
                self.assertEqual(body["columns"], ["region", "total"])
                self.assertIsNotNone(body["suggestion"])
                self.assertEqual(body["suggestion"]["type"], "bar")

                # 2. Validation rejects bad SQL.
                r = await client.post(
                    "/api/v1/kpi/kpis/preview",
                    json={"query_text": "DROP TABLE customers"},
                )
                self.assertEqual(r.status_code, 400)

                # 3. Create a KPI.
                r = await client.post("/api/v1/kpi/kpis", json={
                    "name": "Revenue by region",
                    "description": "Total revenue grouped by region",
                    "query_text":
                        "SELECT region, SUM(revenue) AS total FROM customers GROUP BY region",
                    "chart_config": {"type": "bar", "config": {
                        "category_column": "region", "value_column": "total",
                    }},
                })
                self.assertEqual(r.status_code, 201, r.text)
                kpi = r.json()
                kpi_id = kpi["kpi_id"]
                self.assertIsNotNone(kpi["current_version_id"])
                self.assertEqual(len(kpi["versions"]), 1)
                self.assertEqual(kpi["versions"][0]["version_no"], 1)

                # 4. List shows it.
                r = await client.get("/api/v1/kpi/kpis")
                self.assertEqual(r.status_code, 200)
                listing = r.json()
                self.assertEqual(listing["total"], 1)
                self.assertEqual(listing["items"][0]["chart_type"], "bar")

                # 5. Run live.
                r = await client.post(f"/api/v1/kpi/kpis/{kpi_id}/run")
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["row_count"], 2)

                # 6. Update — query change creates v2.
                r = await client.put(f"/api/v1/kpi/kpis/{kpi_id}", json={
                    "name": "Revenue by region (renamed)",
                    "query_text":
                        "SELECT region, COUNT(*) AS n FROM customers GROUP BY region",
                    "chart_config": {"type": "bar", "config": {
                        "category_column": "region", "value_column": "n",
                    }},
                })
                self.assertEqual(r.status_code, 200, r.text)
                updated = r.json()
                self.assertEqual(updated["name"], "Revenue by region (renamed)")
                self.assertEqual(len(updated["versions"]), 2)
                self.assertEqual(updated["versions"][0]["version_no"], 2)

                # 7. Soft delete.
                r = await client.delete(f"/api/v1/kpi/kpis/{kpi_id}")
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.json()["deleted"])

                # 8. List excludes inactive by default.
                r = await client.get("/api/v1/kpi/kpis")
                self.assertEqual(r.json()["total"], 0)
                r = await client.get("/api/v1/kpi/kpis?include_inactive=true")
                self.assertEqual(r.json()["total"], 1)

        _run(go())

    def test_preview_records_audit_run(self):
        async def go():
            async with self._client() as client:
                r = await client.post("/api/v1/kpi/kpis/preview", json={
                    "query_text": "SELECT COUNT(*) FROM customers",
                })
                self.assertEqual(r.status_code, 200)

            from kpi_studio.deps import get_config
            from kpi_studio.models import KpiQueryRun
            Session = get_config().metadata_session_factory
            with Session() as db:
                count = db.query(KpiQueryRun).count()
                self.assertGreater(count, 0)

        _run(go())


# ---------------------------------------------------------------------------
# Phase C — Smart Builder authoring round-trip.
#
# Separate class so each test gets a fresh app + DB (the legacy
# KpiCrudTests.test_full_lifecycle assumes it's the only KPI in the
# system and would conflict with rows created here).
#
# We don't invoke ``/run`` on builder-mode KPIs: the compiler emits
# T-SQL (TOP N, [bracket-quotes]) and the test target is SQLite, which
# doesn't accept that syntax. Persistence + round-trip is what matters
# at the API layer; the compiler itself is exhaustively tested in
# ``test_spec_compiler.py``.
# ---------------------------------------------------------------------------

class KpiBuilderModeTests(unittest.TestCase):
    def setUp(self):
        self.app = _build_app()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    def test_create_with_builder_spec_compiles_and_persists_round_trip(self):
        async def go():
            async with self._client() as client:
                spec = {
                    "chart_type": "bar",
                    "source": {"name": "customers"},
                    "wells": {
                        "axis":   [{"column": "region"}],
                        "values": [{"column": "revenue", "agg": "SUM"}],
                    },
                    "top_n": 5,
                }
                r = await client.post("/api/v1/kpi/kpis", json={
                    "name": "Revenue by region (builder)",
                    "builder_spec": spec,
                })
                self.assertEqual(r.status_code, 201, r.text)
                created = r.json()
                self.assertIn("FROM [customers]", created["query_text"])
                self.assertIn("GROUP BY [customers].[region]", created["query_text"])
                self.assertIn("TOP 5", created["query_text"])
                self.assertEqual(created["chart_config"]["type"], "bar")
                self.assertEqual(created["builder_spec"]["chart_type"], "bar")
                self.assertEqual(
                    created["builder_spec"]["wells"]["values"][0]["agg"], "SUM",
                )
        _run(go())

    def test_create_without_builder_spec_or_query_text_rejected(self):
        async def go():
            async with self._client() as client:
                r = await client.post("/api/v1/kpi/kpis", json={"name": "Empty"})
                self.assertIn(r.status_code, (400, 422))
        _run(go())

    def test_update_with_new_builder_spec_creates_new_version(self):
        async def go():
            async with self._client() as client:
                r = await client.post("/api/v1/kpi/kpis", json={
                    "name": "Customer scorecard",
                    "builder_spec": {
                        "chart_type": "scorecard",
                        "source": {"name": "customers"},
                        "wells": {"value": [
                            {"column": "revenue", "agg": "SUM"},
                        ]},
                    },
                })
                kpi_id = r.json()["kpi_id"]
                r = await client.put(f"/api/v1/kpi/kpis/{kpi_id}", json={
                    "builder_spec": {
                        "chart_type": "scorecard",
                        "source": {"name": "customers"},
                        "wells": {"value": [
                            {"column": "id", "agg": "COUNT_DISTINCT"},
                        ]},
                    },
                })
                self.assertEqual(r.status_code, 200, r.text)
                detail = r.json()
                self.assertEqual(len(detail["versions"]), 2)
                self.assertIn("COUNT(DISTINCT [customers].[id])", detail["query_text"])
                self.assertEqual(
                    detail["builder_spec"]["wells"]["value"][0]["agg"],
                    "COUNT_DISTINCT",
                )
        _run(go())

    def test_update_to_raw_sql_clears_builder_spec(self):
        async def go():
            async with self._client() as client:
                r = await client.post("/api/v1/kpi/kpis", json={
                    "name": "Switch to raw",
                    "builder_spec": {
                        "chart_type": "bar",
                        "source": {"name": "customers"},
                        "wells": {
                            "axis":   [{"column": "region"}],
                            "values": [{"column": "revenue", "agg": "SUM"}],
                        },
                    },
                })
                kpi_id = r.json()["kpi_id"]
                r = await client.put(f"/api/v1/kpi/kpis/{kpi_id}", json={
                    "query_text":
                        "SELECT region, SUM(revenue) AS total FROM customers GROUP BY region",
                    "chart_config": {"type": "bar", "config": {
                        "category_column": "region", "value_column": "total",
                    }},
                })
                self.assertEqual(r.status_code, 200, r.text)
                self.assertIsNone(r.json()["builder_spec"])
                self.assertIn("SELECT region", r.json()["query_text"])
        _run(go())

    def test_invalid_spec_returns_compile_error(self):
        async def go():
            async with self._client() as client:
                r = await client.post("/api/v1/kpi/kpis", json={
                    "name": "Bad ident",
                    "builder_spec": {
                        "chart_type": "bar",
                        "source": {"name": "customers"},
                        "wells": {
                            "axis":   [{"column": "region; DROP TABLE x"}],
                            "values": [{"column": "revenue", "agg": "SUM"}],
                        },
                    },
                })
                self.assertEqual(r.status_code, 400, r.text)
                self.assertEqual(
                    r.json()["detail"]["error"], "builder_compile_failed",
                )
        _run(go())


if __name__ == "__main__":
    unittest.main()
