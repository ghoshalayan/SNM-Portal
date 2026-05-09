"""Smart-analysis chatbot tests — Phase B1.

Stub provider replays canned tool-use turns; the chat service drives
the same A7 agent loop the KPI editor uses, so we get the full
prompt → SQL → execute → persist round-trip without real network calls.
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from collections import deque

import httpx
from fastapi import FastAPI
from sqlalchemy import (
    Column, Integer, MetaData, String, Table, create_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from kpi_studio import KpiStudioConfig, create_router
from kpi_studio.models import (
    KpiBase, KpiChatMessage, KpiChatSession,
)
from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmResult, LlmToolCall, LlmToolResult,
)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeUser:
    user_id = 1
    company_id = 42
    role_id = 10
    is_super_admin = True


class _OtherUser:
    """A second user for owner-isolation tests."""
    user_id = 999
    company_id = 42
    role_id = 11
    is_super_admin = False


# Module-level holder so tests can swap the active user without rebuilding the app.
_active_user: dict = {"u": FakeUser()}


class ScriptedToolProvider(LlmProvider):
    """Plays back a queue of scripted tool-use turns. Each item is
    either a list of (name, args) tuples or a plain string.

    ``complete_script`` is a separate queue feeding the (no-tools)
    ``complete`` method — used by the B3 insight + summary passes. Each
    item is the literal text to return (typically JSON for the insight
    pass, plain prose for the summariser). When empty, a harmless
    "not used" string is returned so legacy tests that don't care still
    work — those tests then see ``insight=None`` in the assistant row,
    which is the expected graceful-degrade behaviour."""
    name = "stub-chat"

    def __init__(self, script, complete_script=None):
        self._script = deque(script)
        self._complete_script = deque(complete_script or [])
        self.complete_calls: list[list] = []

    def complete(self, messages, *, json_mode=False, max_tokens=None, temperature=0.2) -> LlmResult:
        # Capture the call so tests can inspect what the insight /
        # summariser passes saw — we use this to assert the summariser
        # actually ran when expected.
        self.complete_calls.append(list(messages))
        if self._complete_script:
            text = self._complete_script.popleft()
        else:
            text = "not used"
        return LlmResult(
            text=text, model="stub-1", latency_ms=2,
            usage={"total_tokens": 12},
        )

    def complete_with_tools(self, messages, tools, *, max_tokens=None, temperature=0.2):
        if not self._script:
            raise AssertionError("Test ran out of scripted turns.")
        turn = self._script.popleft()

        if isinstance(turn, str):
            return LlmToolResult(
                tool_calls=[],
                content=turn,
                raw_assistant_message={"role": "assistant", "content": turn},
                model="stub-1", latency_ms=4,
                usage={"total_tokens": 25},
            )

        tool_calls: list[LlmToolCall] = []
        raw_tool_calls: list[dict] = []
        for i, (name, args) in enumerate(turn):
            tc_id = f"call_{i}_{name}"
            tool_calls.append(LlmToolCall(id=tc_id, name=name, arguments=dict(args)))
            raw_tool_calls.append({
                "id": tc_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            })
        return LlmToolResult(
            tool_calls=tool_calls,
            content="",
            raw_assistant_message={
                "role": "assistant", "content": None, "tool_calls": raw_tool_calls,
            },
            model="stub-1", latency_ms=5,
            usage={"total_tokens": 30},
        )


def _build_app(provider=None):
    """Build a FastAPI test app + seed a tiny dataset for the agent's
    peek_distinct_values / executor calls."""
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
        Column("name", String(50), nullable=False),
        Column("region", String(50)),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(md.tables["events"].insert(), [
            {"id": 1, "name": "alpha", "region": "North"},
            {"id": 2, "name": "beta",  "region": "South"},
            {"id": 3, "name": "gamma", "region": "North"},
        ])

    Session = sessionmaker(bind=engine)
    app = FastAPI()

    def _auth():
        return _active_user["u"]

    app.include_router(create_router(KpiStudioConfig(
        auth_dep=_auth,
        metadata_session_factory=Session,
        target_engine=engine,
        tenant_resolver=lambda u: u.company_id,
        permission_checker=lambda u, code: True,
        llm_provider=provider,
    )), prefix="/api/v1/kpi")
    return app, Session


class _Base(unittest.TestCase):
    def setUp(self):
        _active_user["u"] = FakeUser()
        # Disable Pre-flight in tests — every test below scripts the
        # main agent's tool-use turns directly. Pre-flight would
        # consume a turn before the agent ever runs, busting the
        # script. KPI_PREFLIGHT_ENABLED=false flips the
        # settings_service env-fallback so the test app skips the
        # Planner ↔ Resolver loop. Cleaned up in tearDown.
        self._prev_pf = os.environ.get("KPI_PREFLIGHT_ENABLED")
        os.environ["KPI_PREFLIGHT_ENABLED"] = "false"

    def tearDown(self):
        if self._prev_pf is None:
            os.environ.pop("KPI_PREFLIGHT_ENABLED", None)
        else:
            os.environ["KPI_PREFLIGHT_ENABLED"] = self._prev_pf

    def _client(self, provider=None):
        app, Session = _build_app(provider)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ), Session


class SessionLifecycleTests(_Base):
    def test_create_get_rename_delete(self):
        async def go():
            client, _ = self._client()
            async with client as c:
                # Create — empty body, server auto-derives nothing yet.
                r = await c.post("/api/v1/kpi/chat/sessions", json={})
                self.assertEqual(r.status_code, 201, r.text)
                sid = r.json()["chat_session_id"]
                self.assertEqual(r.json()["messages"], [])

                # Get
                r = await c.get(f"/api/v1/kpi/chat/sessions/{sid}")
                self.assertEqual(r.status_code, 200)

                # Rename
                r = await c.put(f"/api/v1/kpi/chat/sessions/{sid}", json={
                    "title": "Q3 deep dive",
                })
                self.assertEqual(r.json()["title"], "Q3 deep dive")

                # List shows it
                r = await c.get("/api/v1/kpi/chat/sessions")
                self.assertEqual(r.json()["total"], 1)
                self.assertEqual(r.json()["items"][0]["title"], "Q3 deep dive")

                # Soft delete
                r = await c.delete(f"/api/v1/kpi/chat/sessions/{sid}")
                self.assertEqual(r.status_code, 200)

                # Hidden from list
                r = await c.get("/api/v1/kpi/chat/sessions")
                self.assertEqual(r.json()["total"], 0)

        _run(go())

    def test_owner_isolation(self):
        async def go():
            client, _ = self._client()
            async with client as c:
                # User 1 creates a session
                _active_user["u"] = FakeUser()
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]

                # User 2 in same company shouldn't see / fetch it
                _active_user["u"] = _OtherUser()
                self.assertEqual(
                    (await c.get(f"/api/v1/kpi/chat/sessions/{sid}")).status_code, 404,
                )
                listing = await c.get("/api/v1/kpi/chat/sessions")
                self.assertEqual(listing.json()["total"], 0)

        _run(go())


class TurnPipelineTests(_Base):
    def test_turn_runs_agent_and_persists_both_messages(self):
        async def go():
            stub = ScriptedToolProvider(script=[
                # Agent walks: list_tables → describe_table → propose_sql.
                [("list_tables", {})],
                [("describe_table", {"name": "events"})],
                [("propose_sql", {
                    "sql": "SELECT region, COUNT(*) AS n FROM events GROUP BY region",
                    "explanation": "Event count by region.",
                })],
            ])
            client, Session = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                r = await c.post(
                    f"/api/v1/kpi/chat/sessions/{sid}/turn",
                    json={"prompt": "How many events per region?"},
                )
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                user = body["user_message"]
                ai = body["assistant_message"]

                # User echo
                self.assertEqual(user["role"], "user")
                self.assertEqual(user["content"], "How many events per region?")
                self.assertIsNone(user["sql"])

                # Assistant payload — SQL + executed result + agent steps
                self.assertEqual(ai["role"], "assistant")
                self.assertIn("SELECT", ai["sql"].upper())
                self.assertEqual(ai["result_columns"], ["region", "n"])
                # Two regions, two rows.
                self.assertEqual(len(ai["result_rows"]), 2)
                self.assertTrue(ai["succeeded"])
                self.assertGreaterEqual(len(ai["agent_steps"]), 1)

                # B2 — chart suggestion populated from the result shape.
                # 2 rows × (string + numeric) → chart_picker emits a bar.
                self.assertIsNotNone(ai["chart_config"])
                self.assertEqual(ai["chart_config"]["type"], "bar")

                # Auto-derived title from the first prompt
                r = await c.get(f"/api/v1/kpi/chat/sessions/{sid}")
                self.assertIn("How many events", r.json()["title"])
                # 2 messages stored in DB
                with Session() as db:
                    self.assertEqual(
                        db.query(KpiChatMessage)
                        .filter(KpiChatMessage.chat_session_id == sid).count(),
                        2,
                    )

        _run(go())

    def test_turn_without_provider_returns_failure_message(self):
        async def go():
            # No provider configured — chat_service should record an
            # assistant message with succeeded=False and a clear hint.
            client, _ = self._client(provider=None)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                r = await c.post(
                    f"/api/v1/kpi/chat/sessions/{sid}/turn",
                    json={"prompt": "anything"},
                )
                self.assertEqual(r.status_code, 200, r.text)
                ai = r.json()["assistant_message"]
                self.assertFalse(ai["succeeded"])
                # Per the chat_service contract, the technical error
                # code is logged + on the abort step but cleared from
                # the persisted ``error`` field — the friendly message
                # in ``content`` is the only thing the user sees.
                self.assertIsNone(ai["error"])
                self.assertIn("disabled", ai["content"].lower())
                self.assertIn("provider", ai["content"].lower())
        _run(go())

    def test_unsafe_proposed_sql_is_recorded_as_failed_turn(self):
        async def go():
            stub = ScriptedToolProvider(script=[
                [("propose_sql", {
                    "sql": "DROP TABLE events",
                    "explanation": "Whoops.",
                })],
            ])
            client, _ = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                r = await c.post(
                    f"/api/v1/kpi/chat/sessions/{sid}/turn",
                    json={"prompt": "trash everything"},
                )
                ai = r.json()["assistant_message"]
                self.assertFalse(ai["succeeded"])
                # Validator caught the DROP before execution — no result rows.
                self.assertIsNone(ai["result_columns"])
                # The user gets a friendly retry message; the technical
                # error code is on the abort step (cleared from
                # ``error`` to keep the bubble clean). Verify the
                # message is non-empty (i.e., we actually rendered
                # something for the user, not a blank failure).
                self.assertIsNone(ai["error"])
                self.assertTrue(ai["content"])
                # SQL was proposed (the unsafe DROP) and is recorded
                # so admins can audit — but it was never executed.
                self.assertIn("drop", (ai["sql"] or "").lower())
        _run(go())


class HistoryRetrievalTests(_Base):
    def test_get_session_returns_messages_chronologically(self):
        async def go():
            stub = ScriptedToolProvider(script=[
                [("propose_sql", {
                    "sql": "SELECT 1 AS x",
                    "explanation": "One.",
                })],
                [("propose_sql", {
                    "sql": "SELECT 2 AS x",
                    "explanation": "Two.",
                })],
            ])
            client, _ = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                await c.post(f"/api/v1/kpi/chat/sessions/{sid}/turn", json={"prompt": "first"})
                await c.post(f"/api/v1/kpi/chat/sessions/{sid}/turn", json={"prompt": "second"})

                r = await c.get(f"/api/v1/kpi/chat/sessions/{sid}")
                msgs = r.json()["messages"]
                # 2 turns × (user + assistant) = 4 messages, ordered by created_at asc
                self.assertEqual(len(msgs), 4)
                self.assertEqual([m["role"] for m in msgs],
                                 ["user", "assistant", "user", "assistant"])
                self.assertEqual(msgs[0]["content"], "first")
                self.assertEqual(msgs[2]["content"], "second")
        _run(go())


class InsightAndSummaryTests(_Base):
    """Phase B3 — second LLM pass that adds an insight + recommendations
    to each successful turn, and rolling-summary compaction once a
    session grows past the threshold."""

    def test_insight_pass_populates_narrative_and_recommendations(self):
        async def go():
            stub = ScriptedToolProvider(
                script=[
                    [("propose_sql", {
                        "sql": "SELECT region, COUNT(*) AS n FROM events GROUP BY region",
                        "explanation": "Event count by region.",
                    })],
                ],
                complete_script=[
                    json.dumps({
                        "narrative": "North leads with 2 events; South has 1.",
                        "recommendations": [
                            "Compare to last month",
                            "Drill into North by event type",
                        ],
                    }),
                ],
            )
            client, _ = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                r = await c.post(
                    f"/api/v1/kpi/chat/sessions/{sid}/turn",
                    json={"prompt": "How many events per region?"},
                )
                ai = r.json()["assistant_message"]
                self.assertTrue(ai["succeeded"])
                self.assertIn("North leads", ai["insight"] or "")
                self.assertEqual(len(ai["recommendations"]), 2)
                self.assertIn("last month", ai["recommendations"][0])
                # Token + duration accounting includes the insight pass.
                self.assertGreaterEqual(ai["tokens"], 12)
        _run(go())

    def test_insight_pass_failure_degrades_silently(self):
        async def go():
            stub = ScriptedToolProvider(
                script=[
                    [("propose_sql", {
                        "sql": "SELECT 1 AS x",
                        "explanation": "One.",
                    })],
                ],
                # Provider returns garbage — JSON parse fails, message
                # still saves with insight=null and the turn succeeds.
                complete_script=["this is not json at all"],
            )
            client, _ = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                r = await c.post(
                    f"/api/v1/kpi/chat/sessions/{sid}/turn",
                    json={"prompt": "anything"},
                )
                ai = r.json()["assistant_message"]
                self.assertTrue(ai["succeeded"])
                self.assertIsNone(ai["insight"])
                self.assertIsNone(ai["recommendations"])
        _run(go())

    def test_rolling_summary_compacts_after_threshold(self):
        async def go():
            # Default: KEEP_LAST_PAIRS=2 + COMPACT_EVERY_PAIRS=3 = 5 pairs.
            # We run 5 successful turns and expect the session's
            # rolling_summary to be populated by the 5th.
            propose = lambda i: [("propose_sql", {  # noqa: E731 — local helper
                "sql": f"SELECT {i} AS x",
                "explanation": f"Number {i}.",
            })]
            stub = ScriptedToolProvider(
                script=[propose(i) for i in range(1, 6)],
                # 5 insight responses + 1 summariser response. The
                # insight responses are JSON; the summary is plain prose.
                complete_script=(
                    [json.dumps({
                        "narrative": f"Returned {i}.",
                        "recommendations": [],
                    }) for i in range(1, 6)]
                    + ["The user explored small integer queries. North "
                       "and South regions were touched. No anomalies."]
                ),
            )
            client, _ = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                for i in range(5):
                    r = await c.post(
                        f"/api/v1/kpi/chat/sessions/{sid}/turn",
                        json={"prompt": f"prompt {i + 1}"},
                    )
                    self.assertEqual(r.status_code, 200, r.text)

                # After 5 pairs, the summariser should have run.
                detail = (await c.get(f"/api/v1/kpi/chat/sessions/{sid}")).json()
                self.assertIsNotNone(detail["rolling_summary"])
                self.assertIn("integer queries", detail["rolling_summary"])
                # All 10 messages preserved — summariser doesn't delete history.
                self.assertEqual(len(detail["messages"]), 10)
        _run(go())

    def test_rolling_summary_skips_below_threshold(self):
        async def go():
            stub = ScriptedToolProvider(
                script=[
                    [("propose_sql", {"sql": "SELECT 1 AS x", "explanation": "One."})],
                    [("propose_sql", {"sql": "SELECT 2 AS x", "explanation": "Two."})],
                ],
                # 2 insight responses, no summary needed.
                complete_script=[
                    json.dumps({"narrative": "n", "recommendations": []}),
                    json.dumps({"narrative": "n", "recommendations": []}),
                ],
            )
            client, _ = self._client(stub)
            async with client as c:
                sid = (await c.post("/api/v1/kpi/chat/sessions", json={})).json()["chat_session_id"]
                for prompt in ("first", "second"):
                    await c.post(
                        f"/api/v1/kpi/chat/sessions/{sid}/turn", json={"prompt": prompt},
                    )
                detail = (await c.get(f"/api/v1/kpi/chat/sessions/{sid}")).json()
                # 2 pairs is below threshold — summary stays unset.
                self.assertIsNone(detail["rolling_summary"])
        _run(go())


if __name__ == "__main__":
    unittest.main()
