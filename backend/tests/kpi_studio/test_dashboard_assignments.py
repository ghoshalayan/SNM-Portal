"""Dashboard assignment (Phase A4) tests.

Covers:
  * Owner / SuperAdmin can grant + revoke; peers cannot
  * Validator rejects neither / both for role_id + user_id
  * Re-granting an existing role/user is idempotent
  * Cross-tenant role assignment makes the dashboard visible
  * Direct user assignment makes a private dashboard visible
  * Revoke removes visibility
  * Listing assignments is restricted to managers
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
from kpi_studio.models import KpiBase


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeUser:
    def __init__(self, user_id, company_id, role_id=10, is_super_admin=False):
        self.user_id = user_id
        self.company_id = company_id
        self.role_id = role_id
        self.is_super_admin = is_super_admin


# Module-level slot so tests can swap the active user between requests
# without rebuilding the FastAPI app.
_active_user = {"u": FakeUser(1, 42, is_super_admin=True)}


def _build_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiBase.metadata.create_all(engine)
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
        # Default actor: SuperAdmin in company 42.
        _active_user["u"] = FakeUser(1, 42, is_super_admin=True)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )


class ValidatorTests(_Base):
    def test_must_set_exactly_one_target(self):
        async def go():
            async with self._client() as c:
                d = (await c.post("/api/v1/kpi/dashboards", json={"name": "D"})).json()
                did = d["dashboard_id"]

                # Neither set → 422 from Pydantic.
                r = await c.post(f"/api/v1/kpi/dashboards/{did}/assignments", json={})
                self.assertEqual(r.status_code, 422)

                # Both set → 422 from the model_validator.
                r = await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"role_id": 5, "user_id": 6},
                )
                self.assertEqual(r.status_code, 422)
        _run(go())


class GrantRevokeTests(_Base):
    def test_owner_can_grant_and_revoke(self):
        async def go():
            async with self._client() as c:
                # Acting as owner (non-SuperAdmin so we test the owner branch).
                _active_user["u"] = FakeUser(7, 42, role_id=10)
                d = (await c.post("/api/v1/kpi/dashboards", json={"name": "Mine"})).json()
                did = d["dashboard_id"]

                # Grant by role.
                r = await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"role_id": 99},
                )
                self.assertEqual(r.status_code, 201, r.text)
                aid = r.json()["assignment_id"]
                self.assertEqual(r.json()["role_id"], 99)
                self.assertIsNone(r.json()["user_id"])

                # List it back.
                r = await c.get(f"/api/v1/kpi/dashboards/{did}/assignments")
                self.assertEqual(r.status_code, 200)
                self.assertEqual(len(r.json()), 1)

                # Revoke.
                r = await c.delete(f"/api/v1/kpi/dashboards/{did}/assignments/{aid}")
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.json()["deleted"])

                r = await c.get(f"/api/v1/kpi/dashboards/{did}/assignments")
                self.assertEqual(r.json(), [])
        _run(go())

    def test_peer_cannot_grant_or_list(self):
        async def go():
            async with self._client() as c:
                # Owner creates the board.
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Shared", "scope": "company",
                })).json()
                did = d["dashboard_id"]

                # Peer tries to grant — 403.
                _active_user["u"] = FakeUser(99, 42)
                r = await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"role_id": 5},
                )
                self.assertEqual(r.status_code, 403)

                # Peer tries to list — 403.
                r = await c.get(f"/api/v1/kpi/dashboards/{did}/assignments")
                self.assertEqual(r.status_code, 403)
        _run(go())

    def test_grant_is_idempotent(self):
        async def go():
            async with self._client() as c:
                d = (await c.post("/api/v1/kpi/dashboards", json={"name": "D"})).json()
                did = d["dashboard_id"]

                first = await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"user_id": 42},
                )
                second = await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"user_id": 42},
                )
                self.assertEqual(first.status_code, 201)
                # The second call returns the same row, no duplicate.
                self.assertEqual(
                    first.json()["assignment_id"],
                    second.json()["assignment_id"],
                )

                listing = await c.get(f"/api/v1/kpi/dashboards/{did}/assignments")
                self.assertEqual(len(listing.json()), 1)
        _run(go())


class VisibilityExpansionTests(_Base):
    def test_user_assignment_grants_visibility_on_private_board(self):
        async def go():
            async with self._client() as c:
                # Owner (user 7) creates a PRIVATE board.
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Private", "scope": "user",
                })).json()
                did = d["dashboard_id"]

                # User 99 in same company shouldn't see it yet.
                _active_user["u"] = FakeUser(99, 42, role_id=10)
                listing = (await c.get("/api/v1/kpi/dashboards")).json()
                self.assertNotIn(did, [d["dashboard_id"] for d in listing["items"]])
                self.assertEqual(
                    (await c.get(f"/api/v1/kpi/dashboards/{did}")).status_code, 404,
                )

                # Owner grants user 99.
                _active_user["u"] = FakeUser(7, 42)
                await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"user_id": 99},
                )

                # Now user 99 sees it.
                _active_user["u"] = FakeUser(99, 42, role_id=10)
                listing = (await c.get("/api/v1/kpi/dashboards")).json()
                self.assertIn(did, [d["dashboard_id"] for d in listing["items"]])
                r = await c.get(f"/api/v1/kpi/dashboards/{did}")
                self.assertEqual(r.status_code, 200)
        _run(go())

    def test_role_assignment_grants_visibility(self):
        async def go():
            async with self._client() as c:
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Role-restricted", "scope": "user",
                })).json()
                did = d["dashboard_id"]

                # Grant role 55.
                await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"role_id": 55},
                )

                # User with role 55 sees it.
                _active_user["u"] = FakeUser(99, 42, role_id=55)
                r = await c.get(f"/api/v1/kpi/dashboards/{did}")
                self.assertEqual(r.status_code, 200)

                # User with role 60 does not.
                _active_user["u"] = FakeUser(100, 42, role_id=60)
                self.assertEqual(
                    (await c.get(f"/api/v1/kpi/dashboards/{did}")).status_code, 404,
                )
        _run(go())

    def test_revoke_removes_visibility(self):
        async def go():
            async with self._client() as c:
                _active_user["u"] = FakeUser(7, 42)
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Toggle", "scope": "user",
                })).json()
                did = d["dashboard_id"]

                grant = await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"user_id": 99},
                )
                aid = grant.json()["assignment_id"]

                _active_user["u"] = FakeUser(99, 42, role_id=10)
                self.assertEqual(
                    (await c.get(f"/api/v1/kpi/dashboards/{did}")).status_code, 200,
                )

                _active_user["u"] = FakeUser(7, 42)
                await c.delete(f"/api/v1/kpi/dashboards/{did}/assignments/{aid}")

                _active_user["u"] = FakeUser(99, 42, role_id=10)
                self.assertEqual(
                    (await c.get(f"/api/v1/kpi/dashboards/{did}")).status_code, 404,
                )
        _run(go())

    def test_assignment_overrides_company_isolation(self):
        """SuperAdmin can intentionally cross-tenant grant. The user just
        gets the dashboard regardless of company match."""
        async def go():
            async with self._client() as c:
                # SuperAdmin (default fixture) creates board in company 42.
                d = (await c.post("/api/v1/kpi/dashboards", json={
                    "name": "Cross-tenant", "scope": "user",
                })).json()
                did = d["dashboard_id"]

                # Grant user 200 (in a different company).
                await c.post(
                    f"/api/v1/kpi/dashboards/{did}/assignments",
                    json={"user_id": 200},
                )

                # User 200 in company 99 can now see it.
                _active_user["u"] = FakeUser(200, 99, role_id=77)
                r = await c.get(f"/api/v1/kpi/dashboards/{did}")
                self.assertEqual(r.status_code, 200)
        _run(go())


if __name__ == "__main__":
    unittest.main()
