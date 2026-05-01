"""Tests for the time-period resolver and the relaxed sql_safety
parameter allow-list (Phase A5)."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI
from sqlalchemy import (
    Column, DateTime, Integer, MetaData, String, Table, create_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kpi_studio import KpiStudioConfig, create_router
from kpi_studio.models import KpiBase
from kpi_studio.services.sql_safety import SqlSafetyError, validate_select_query
from kpi_studio.services.time_periods import (
    InvalidPeriodError, resolve_period,
)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Period resolver
# ---------------------------------------------------------------------------

class PeriodResolverTests(unittest.TestCase):
    def setUp(self):
        # Pin "now" to a stable timestamp so the rolling presets are testable.
        self.now = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)

    def test_none_returns_none(self):
        self.assertIsNone(resolve_period(None))
        self.assertIsNone(resolve_period(""))

    def test_daily_is_24h(self):
        s, e = resolve_period("daily", now=self.now)
        self.assertEqual(e, self.now)
        self.assertEqual(self.now - s, timedelta(days=1))

    def test_weekly_is_7d(self):
        s, e = resolve_period("weekly", now=self.now)
        self.assertEqual(self.now - s, timedelta(days=7))

    def test_monthly_is_30d(self):
        s, e = resolve_period("monthly", now=self.now)
        self.assertEqual(self.now - s, timedelta(days=30))

    def test_quarterly_is_90d(self):
        s, e = resolve_period("quarterly", now=self.now)
        self.assertEqual(self.now - s, timedelta(days=90))

    def test_yearly_is_365d(self):
        s, e = resolve_period("yearly", now=self.now)
        self.assertEqual(self.now - s, timedelta(days=365))

    def test_last_5_years(self):
        s, e = resolve_period("last_5_years", now=self.now)
        self.assertEqual(self.now - s, timedelta(days=5 * 365))

    def test_custom_requires_both_dates(self):
        with self.assertRaises(InvalidPeriodError):
            resolve_period("custom", now=self.now)
        with self.assertRaises(InvalidPeriodError):
            resolve_period("custom", start_date=self.now, now=self.now)

    def test_custom_passthrough(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 4, 1, tzinfo=timezone.utc)
        s, e = resolve_period("custom", start_date=start, end_date=end, now=self.now)
        self.assertEqual(s, start)
        self.assertEqual(e, end)

    def test_custom_rejects_inverted_range(self):
        s = datetime(2026, 4, 1, tzinfo=timezone.utc)
        e = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with self.assertRaises(InvalidPeriodError):
            resolve_period("custom", start_date=s, end_date=e, now=self.now)

    def test_unknown_period_rejected(self):
        with self.assertRaises(InvalidPeriodError):
            resolve_period("forever", now=self.now)


# ---------------------------------------------------------------------------
# Validator: :start_date / :end_date allow-list
# ---------------------------------------------------------------------------

class AllowListedParamTests(unittest.TestCase):
    def test_start_and_end_date_accepted(self):
        sql = (
            "SELECT COUNT(*) FROM Quotation "
            "WHERE createdon BETWEEN :start_date AND :end_date"
        )
        # Should not raise.
        safe = validate_select_query(sql, dialect="tsql")
        # Both placeholders survive into the rewritten SQL — the executor
        # will bind them.
        self.assertIn(":start_date", safe.rewritten)
        self.assertIn(":end_date", safe.rewritten)

    def test_other_named_params_rejected(self):
        # Phase I extended the allow-list with :company_id and :user_id;
        # any other arbitrary marker must still be rejected.
        with self.assertRaises(SqlSafetyError) as cm:
            validate_select_query(
                "SELECT * FROM Quotation WHERE userId = :secret_admin_token",
                dialect="tsql",
            )
        self.assertIn("secret_admin_token", str(cm.exception).lower())

    def test_positional_marker_still_rejected(self):
        with self.assertRaises(SqlSafetyError):
            validate_select_query("SELECT * FROM x WHERE id = ?", dialect="tsql")


# ---------------------------------------------------------------------------
# End-to-end: preview with a period actually filters via :start_date/:end_date
# ---------------------------------------------------------------------------

class FakeUser:
    user_id = 1
    company_id = 42
    role_id = 10
    is_super_admin = True


def _build_app_with_dated_table():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KpiBase.metadata.create_all(engine)

    md = MetaData()
    Table(
        "events", md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
        # SQLite stores datetimes as ISO strings; that round-trips fine
        # through the SQLAlchemy ``text()`` parameter binding we use.
        Column("created_at", DateTime),
    )
    md.create_all(engine)

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(md.tables["events"].insert(), [
            {"id": 1, "name": "old", "created_at": now - timedelta(days=200)},
            {"id": 2, "name": "recent", "created_at": now - timedelta(days=3)},
            {"id": 3, "name": "today", "created_at": now - timedelta(hours=2)},
        ])

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
    return app


class TimeBoundPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _build_app_with_dated_table()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    def test_preview_without_period_returns_all_rows(self):
        async def go():
            async with self._client() as c:
                r = await c.post("/api/v1/kpi/kpis/preview", json={
                    "query_text": (
                        "SELECT COUNT(*) AS n FROM events "
                        "WHERE (:start_date IS NULL OR created_at >= :start_date) "
                        "AND (:end_date IS NULL OR created_at <= :end_date)"
                    ),
                })
                self.assertEqual(r.status_code, 200, r.text)
                # No period → SQLAlchemy binds nothing; the COALESCE-style
                # WHERE in our SQL keeps everything.
                self.assertEqual(r.json()["rows"][0][0], 3)
        _run(go())

    def test_preview_weekly_filters_to_recent_rows(self):
        async def go():
            async with self._client() as c:
                r = await c.post("/api/v1/kpi/kpis/preview", json={
                    "query_text": (
                        "SELECT COUNT(*) AS n FROM events "
                        "WHERE created_at BETWEEN :start_date AND :end_date"
                    ),
                    "period": "weekly",
                })
                self.assertEqual(r.status_code, 200, r.text)
                # 7-day window leaves the 3-day-old + today rows but drops
                # the 200-day-old one.
                self.assertEqual(r.json()["rows"][0][0], 2)
        _run(go())

    def test_preview_invalid_period_returns_400(self):
        async def go():
            async with self._client() as c:
                r = await c.post("/api/v1/kpi/kpis/preview", json={
                    "query_text": "SELECT 1",
                    "period": "forever",
                })
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.json()["detail"]["error"], "invalid_period")
        _run(go())

    def test_preview_custom_window(self):
        async def go():
            async with self._client() as c:
                # Window covers the 3-day-old row but excludes today.
                end = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
                start = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
                r = await c.post("/api/v1/kpi/kpis/preview", json={
                    "query_text": (
                        "SELECT COUNT(*) AS n FROM events "
                        "WHERE created_at BETWEEN :start_date AND :end_date"
                    ),
                    "period": "custom",
                    "start_date": start,
                    "end_date": end,
                })
                self.assertEqual(r.status_code, 200, r.text)
                self.assertEqual(r.json()["rows"][0][0], 1)
        _run(go())


if __name__ == "__main__":
    unittest.main()
