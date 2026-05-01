"""Dashboard CRUD + scope visibility tests.

Covers:
  * Create / list / get / update / delete lifecycle
  * Add / move / resize / remove items
  * Layout bulk-update endpoint
  * Per-user vs per-company scope visibility (private vs shared)
  * Owner-only delete on shared dashboards
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

from kpi_studio import KpiStudioConfig, create_router
from kpi_studio.models import KpiBase


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeUser:
    def __init__(self, user_id: int, company_id: int, is_super_admin: bool = False):
        self.user_id = user_id
        self.company_id = company_id
        self.is_super_admin = is_super_admin


# Authentication is a process-global dep — we swap the active user via a
# module-level slot before each request. Cleaner than rebuilding the app.
_active_user = {"u": FakeUser(7, 42)}


def _build_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiBase.metadata.create_all(engine)

    md = MetaData()
    customers = Table(
        "customers", md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
        Column("revenue", Integer),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(customers.insert(), [
            {"id": 1, "name": "Acme", "revenue": 100},
            {"id": 2, "name": "Beta", "revenue": 200},
        ])

    Session = sessionmaker(bind=engine)

    def _auth() -> FakeUser:
        return _active_user["u"]

    app = FastAPI()
    app.include_router(create_router(KpiStudioConfig(
        auth_dep=_auth,
        metadata_session_factory=Session,
        target_engine=engine,
        tenant_resolver=lambda u: u.company_id,
        permission_checker=lambda u, code: True,
    )), prefix="/api/v1/kpi")
    return app


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _build_app()

    def setUp(self):
        # Reset acting user for each test.
        _active_user["u"] = FakeUser(7, 42)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    async def _create_kpi(self, client, name: str = "Revenue total") -> int:
        r = await client.post("/api/v1/kpi/kpis", json={
            "name": name,
            "query_text": "SELECT SUM(revenue) AS total FROM customers",
            "chart_config": {"type": "scorecard", "config": {"value_column": "total"}},
        })
        assert r.status_code == 201, r.text
        return r.json()["kpi_id"]


class CrudTests(_Base):
    def test_create_list_get_delete(self):
        async def go():
            async with self._client() as c:
                # Create
                r = await c.post("/api/v1/kpi/dashboards", json={
                    "name": "My private board",
                    "scope": "user",
                })
                self.assertEqual(r.status_code, 201, r.text)
                d = r.json()
                self.assertEqual(d["scope"], "user")
                self.assertEqual(d["owner_user_id"], 7)
                self.assertEqual(d["company_id"], 42)
                self.assertEqual(d["items"], [])

                # List shows it
                r = await c.get("/api/v1/kpi/dashboards")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["total"], 1)
                self.assertEqual(r.json()["items"][0]["item_count"], 0)

                # Detail
                r = await c.get(f"/api/v1/kpi/dashboards/{d['dashboard_id']}")
                self.assertEqual(r.status_code, 200)

                # Soft delete
                r = await c.delete(f"/api/v1/kpi/dashboards/{d['dashboard_id']}")
                self.assertEqual(r.status_code, 200)

                r = await c.get("/api/v1/kpi/dashboards")
                self.assertEqual(r.json()["total"], 0)

        _run(go())

    def test_update_metadata_and_scope(self):
        async def go():
            async with self._client() as c:
                r = await c.post("/api/v1/kpi/dashboards", json={"name": "X"})
                did = r.json()["dashboard_id"]

                r = await c.put(f"/api/v1/kpi/dashboards/{did}", json={
                    "name": "X (renamed)",
                    "description": "Now shared",
                    "scope": "company",
                })
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["name"], "X (renamed)")
                self.assertEqual(r.json()["scope"], "company")

        _run(go())

    def test_invalid_scope_rejected(self):
        async def go():
            async with self._client() as c:
                r = await c.post("/api/v1/kpi/dashboards", json={
                    "name": "X", "scope": "global",
                })
                self.assertEqual(r.status_code, 400)

        _run(go())


class ItemTests(_Base):
    def test_add_move_resize_remove_items(self):
        async def go():
            async with self._client() as c:
                kpi_id = await self._create_kpi(c)
                r = await c.post("/api/v1/kpi/dashboards", json={"name": "Board"})
                did = r.json()["dashboard_id"]

                # Add two items
                r = await c.post(f"/api/v1/kpi/dashboards/{did}/items", json={
                    "kpi_id": kpi_id, "size_class": "md",
                })
                self.assertEqual(r.status_code, 201, r.text)
                a = r.json()
                self.assertEqual(a["position"], 0)

                r = await c.post(f"/api/v1/kpi/dashboards/{did}/items", json={
                    "kpi_id": kpi_id, "size_class": "lg",
                })
                b = r.json()
                self.assertEqual(b["position"], 1)

                # Bulk swap positions via /layout
                r = await c.put(f"/api/v1/kpi/dashboards/{did}/layout", json={
                    "items": [
                        {"item_id": a["item_id"], "position": 1, "size_class": "wide"},
                        {"item_id": b["item_id"], "position": 0},
                    ],
                })
                self.assertEqual(r.status_code, 200, r.text)
                items = r.json()["items"]
                positions = {it["item_id"]: it["position"] for it in items}
                self.assertEqual(positions[a["item_id"]], 1)
                self.assertEqual(positions[b["item_id"]], 0)
                sizes = {it["item_id"]: it["size_class"] for it in items}
                self.assertEqual(sizes[a["item_id"]], "wide")

                # Patch a single item
                r = await c.put(f"/api/v1/kpi/dashboards/{did}/items/{a['item_id']}", json={
                    "size_class": "sm", "title_override": "Custom title",
                })
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()["title_override"], "Custom title")

                # Remove
                r = await c.delete(f"/api/v1/kpi/dashboards/{did}/items/{b['item_id']}")
                self.assertEqual(r.status_code, 200)

                r = await c.get(f"/api/v1/kpi/dashboards/{did}")
                self.assertEqual(len(r.json()["items"]), 1)

        _run(go())

    def test_invalid_size_rejected(self):
        async def go():
            async with self._client() as c:
                kpi_id = await self._create_kpi(c)
                r = await c.post("/api/v1/kpi/dashboards", json={"name": "B"})
                did = r.json()["dashboard_id"]
                r = await c.post(f"/api/v1/kpi/dashboards/{did}/items", json={
                    "kpi_id": kpi_id, "size_class": "huge",
                })
                self.assertEqual(r.status_code, 400)

        _run(go())

    def test_layout_rejects_foreign_item(self):
        async def go():
            async with self._client() as c:
                kpi_id = await self._create_kpi(c)
                # Two dashboards
                d1 = (await c.post("/api/v1/kpi/dashboards", json={"name": "D1"})).json()["dashboard_id"]
                d2 = (await c.post("/api/v1/kpi/dashboards", json={"name": "D2"})).json()["dashboard_id"]
                a = (await c.post(f"/api/v1/kpi/dashboards/{d1}/items",
                                  json={"kpi_id": kpi_id})).json()

                # Try to move D1's item via D2's layout endpoint.
                r = await c.put(f"/api/v1/kpi/dashboards/{d2}/layout", json={
                    "items": [{"item_id": a["item_id"], "position": 0}],
                })
                self.assertEqual(r.status_code, 400)

        _run(go())


class GridCoordsTests(_Base):
    """Phase D — Power BI–style 12-column grid coordinates.

    Items must come back with grid_x/y/w/h populated (backfilled from
    size_class for legacy rows), and the layout endpoint must persist
    explicit coords sent by angular-gridster2.
    """

    def test_items_get_backfilled_grid_coords(self):
        async def go():
            async with self._client() as c:
                kpi_id = await self._create_kpi(c)
                did = (await c.post("/api/v1/kpi/dashboards", json={"name": "Grid"})).json()["dashboard_id"]
                # Two items — md (w=12) + lg (w=18) on a 24-col grid.
                # md fits at x=0; lg would overflow (12+18>24) so wraps.
                a = (await c.post(f"/api/v1/kpi/dashboards/{did}/items",
                                  json={"kpi_id": kpi_id, "size_class": "md"})).json()
                b = (await c.post(f"/api/v1/kpi/dashboards/{did}/items",
                                  json={"kpi_id": kpi_id, "size_class": "lg"})).json()
                # First item: x=0, y=0, w=12, h=8
                self.assertEqual(a["grid_x"], 0)
                self.assertEqual(a["grid_y"], 0)
                self.assertEqual(a["grid_w"], 12)
                self.assertEqual(a["grid_h"], 8)
                # Second: lg = w=18. Wraps to next row at y=8 (one row
                # height = grid_h units). x=0 again.
                self.assertEqual(b["grid_x"], 0)
                self.assertEqual(b["grid_y"], 8)
                self.assertEqual(b["grid_w"], 18)
                # Detail GET should reflect the same packing.
                r = await c.get(f"/api/v1/kpi/dashboards/{did}")
                items_by_id = {it["item_id"]: it for it in r.json()["items"]}
                self.assertEqual(items_by_id[a["item_id"]]["grid_x"], 0)
                self.assertEqual(items_by_id[b["item_id"]]["grid_y"], 8)
        _run(go())

    def test_layout_persists_explicit_grid_coords(self):
        async def go():
            async with self._client() as c:
                kpi_id = await self._create_kpi(c)
                did = (await c.post("/api/v1/kpi/dashboards", json={"name": "G"})).json()["dashboard_id"]
                a = (await c.post(f"/api/v1/kpi/dashboards/{did}/items",
                                  json={"kpi_id": kpi_id})).json()

                # Send explicit coords — gridster's drop event maps onto
                # this shape. Server should round-trip them verbatim.
                r = await c.put(f"/api/v1/kpi/dashboards/{did}/layout", json={
                    "items": [{
                        "item_id": a["item_id"], "position": 0,
                        "grid_x": 3, "grid_y": 2, "grid_w": 4, "grid_h": 6,
                    }],
                })
                self.assertEqual(r.status_code, 200, r.text)
                it = r.json()["items"][0]
                self.assertEqual(it["grid_x"], 3)
                self.assertEqual(it["grid_y"], 2)
                self.assertEqual(it["grid_w"], 4)
                self.assertEqual(it["grid_h"], 6)
                # Subsequent GET still has them.
                r = await c.get(f"/api/v1/kpi/dashboards/{did}")
                got = r.json()["items"][0]
                self.assertEqual((got["grid_x"], got["grid_y"], got["grid_w"], got["grid_h"]),
                                 (3, 2, 4, 6))
        _run(go())

    def test_grid_coords_validated(self):
        async def go():
            async with self._client() as c:
                kpi_id = await self._create_kpi(c)
                did = (await c.post("/api/v1/kpi/dashboards", json={"name": "G"})).json()["dashboard_id"]
                a = (await c.post(f"/api/v1/kpi/dashboards/{did}/items",
                                  json={"kpi_id": kpi_id})).json()
                # x out of range — Pydantic 422.
                r = await c.put(f"/api/v1/kpi/dashboards/{did}/layout", json={
                    "items": [{
                        "item_id": a["item_id"], "position": 0,
                        "grid_x": 99, "grid_y": 0, "grid_w": 4, "grid_h": 4,
                    }],
                })
                self.assertEqual(r.status_code, 422, r.text)
        _run(go())


class ScopeVisibilityTests(_Base):
    def test_private_dashboard_invisible_to_other_user_same_company(self):
        async def go():
            async with self._client() as c:
                # User 7 creates a private dashboard
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Mine", "scope": "user",
                })).json()

                # User 9 in the same company shouldn't see it
                _active_user["u"] = FakeUser(9, 42)
                listing = (await c.get("/api/v1/kpi/dashboards")).json()
                self.assertEqual(listing["total"], 0)

                r = await c.get(f"/api/v1/kpi/dashboards/{d['dashboard_id']}")
                self.assertEqual(r.status_code, 404)

        _run(go())

    def test_shared_dashboard_visible_to_other_user_same_company(self):
        async def go():
            async with self._client() as c:
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Team", "scope": "company",
                })).json()

                # Other tests share the in-memory DB, so assert by id presence
                # rather than total count.
                _active_user["u"] = FakeUser(9, 42)
                listing = (await c.get("/api/v1/kpi/dashboards")).json()
                ids = {it["dashboard_id"] for it in listing["items"]}
                self.assertIn(d["dashboard_id"], ids)

                r = await c.get(f"/api/v1/kpi/dashboards/{d['dashboard_id']}")
                self.assertEqual(r.status_code, 200)

        _run(go())

    def test_shared_dashboard_invisible_across_companies(self):
        async def go():
            async with self._client() as c:
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Co42", "scope": "company",
                })).json()

                # Different company
                _active_user["u"] = FakeUser(11, 99)
                listing = (await c.get("/api/v1/kpi/dashboards")).json()
                self.assertEqual(listing["total"], 0)

                r = await c.get(f"/api/v1/kpi/dashboards/{d['dashboard_id']}")
                self.assertEqual(r.status_code, 404)

        _run(go())

    def test_shared_dashboard_only_owner_can_delete(self):
        async def go():
            async with self._client() as c:
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Shared", "scope": "company",
                })).json()
                did = d["dashboard_id"]

                # Same-company peer can edit but NOT delete
                _active_user["u"] = FakeUser(9, 42)
                r = await c.put(f"/api/v1/kpi/dashboards/{did}", json={"name": "Renamed by peer"})
                self.assertEqual(r.status_code, 200)

                r = await c.delete(f"/api/v1/kpi/dashboards/{did}")
                self.assertEqual(r.status_code, 403)

                # Owner can
                _active_user["u"] = FakeUser(7, 42)
                r = await c.delete(f"/api/v1/kpi/dashboards/{did}")
                self.assertEqual(r.status_code, 200)

        _run(go())


if __name__ == "__main__":
    unittest.main()
