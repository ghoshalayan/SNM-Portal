"""Agent (tool-use) NL→SQL tests — Phase A7.

Stub provider replays a scripted sequence of tool calls / final
messages so we can deterministically test:
  * Happy path: model calls list_tables → describe_table → propose_sql.
  * peek_distinct_values runs against the live DB through the executor.
  * Validator surfaces but doesn't void a useful agent answer.
  * Iteration cap fires cleanly with an ``abort`` step.
  * Token budget abort.
  * Audit row written to kpi_nl_run for both success and abort paths.
"""
from __future__ import annotations

import asyncio
import json
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
from kpi_studio.models import KpiBase, KpiNlRun
from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmResult, LlmTool, LlmToolCall, LlmToolResult,
)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class FakeUser:
    user_id = 1
    company_id = 42
    role_id = 10
    is_super_admin = True


class ScriptedToolProvider(LlmProvider):
    """Replays a queue of canned tool-use turns. Each item is either:
      * an iterable of ``(tool_name, args)`` tuples → emitted as tool_calls
      * a string → emitted as a plain content reply (no tool calls)
    """
    name = "stub-agent"

    def __init__(self, script):
        self._script = deque(script)
        # Default usage so the budget calc has numbers; override per turn
        # by passing a dict instead of a list/str.
        self._default_usage = {"total_tokens": 50}

    def complete(self, *args, **kwargs) -> LlmResult:
        # Single-shot path isn't used by the agent. Provide a stub so the
        # protocol is satisfied.
        return LlmResult(text="not used", model="stub", latency_ms=1)

    def complete_with_tools(
        self, messages, tools, *, max_tokens=None, temperature=0.2,
    ) -> LlmToolResult:
        if not self._script:
            raise AssertionError("Test ran out of scripted turns.")

        turn = self._script.popleft()
        usage = self._default_usage

        if isinstance(turn, dict) and "calls" in turn:
            usage = turn.get("usage") or self._default_usage
            tool_calls_spec = turn["calls"]
        elif isinstance(turn, str):
            return LlmToolResult(
                tool_calls=[],
                content=turn,
                raw_assistant_message={"role": "assistant", "content": turn},
                model="stub-1", latency_ms=5, usage=usage,
            )
        else:
            tool_calls_spec = turn

        tool_calls: list[LlmToolCall] = []
        raw_tool_calls: list[dict] = []
        for i, (name, args) in enumerate(tool_calls_spec):
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
                "role": "assistant",
                "content": None,
                "tool_calls": raw_tool_calls,
            },
            model="stub-1", latency_ms=5, usage=usage,
        )


def _build_app(provider, **kwargs):
    """Build a FastAPI test app with the given LLM provider stubbed in.

    Also seeds a small ``customers`` table on the target engine so
    ``peek_distinct_values`` has something to read.
    """
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
        Column("region", String(50)),
    )
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(md.tables["customers"].insert(), [
            {"id": 1, "name": "Acme", "region": "North"},
            {"id": 2, "name": "Beta", "region": "South"},
            {"id": 3, "name": "Gamma", "region": "North"},
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
        llm_provider=provider,
    )), prefix="/api/v1/kpi")
    return app, Session


class _Base(unittest.TestCase):
    def _client(self, provider):
        app, Session = _build_app(provider)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        return client, Session


class HappyPathTests(_Base):
    def test_agent_list_describe_propose(self):
        """Three-step flow: discover tables → describe one → propose SQL."""
        async def go():
            provider = ScriptedToolProvider(script=[
                # Turn 1: model calls list_tables.
                [("list_tables", {})],
                # Turn 2: model describes "customers".
                [("describe_table", {"name": "customers"})],
                # Turn 3: model proposes SQL.
                [("propose_sql", {
                    "sql": "SELECT region, COUNT(*) AS n FROM customers GROUP BY region",
                    "explanation": "Customer count grouped by region.",
                })],
            ])

            client, Session = self._client(provider)
            async with client as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={
                    "prompt": "How many customers in each region?",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertEqual(body["mode"], "agent")
                self.assertIn("SELECT", body["sql"].upper())
                self.assertEqual(body["iterations"], 3)
                self.assertEqual(body["validation"]["ok"], True)
                # Three steps recorded: 2 tool_calls + 1 final.
                step_types = [s["type"] for s in body["steps"]]
                self.assertEqual(step_types.count("tool_call"), 2)
                self.assertEqual(step_types.count("final"), 1)
                # Audit row written.
                with Session() as db:
                    runs = db.query(KpiNlRun).all()
                    self.assertEqual(len(runs), 1)
                    self.assertTrue(runs[0].succeeded)
                    self.assertEqual(runs[0].iterations, 3)

        _run(go())

    def test_peek_distinct_values_hits_live_db(self):
        async def go():
            provider = ScriptedToolProvider(script=[
                [("peek_distinct_values", {"table": "customers", "column": "region", "limit": 10})],
                [("propose_sql", {
                    "sql": "SELECT * FROM customers WHERE region = 'North'",
                    "explanation": "Picked 'North' after seeing the distinct values.",
                })],
            ])

            client, _ = self._client(provider)
            async with client as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={
                    "prompt": "Customers in the North region",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                # peek step output should contain the seed values.
                peek_step = next(
                    s for s in body["steps"] if s.get("tool") == "peek_distinct_values"
                )
                self.assertIsNotNone(peek_step["output"])
                values = peek_step["output"]["values"]
                self.assertIn("North", values)
                self.assertIn("South", values)

        _run(go())

    def test_unsafe_proposed_sql_surfaces_warning(self):
        async def go():
            provider = ScriptedToolProvider(script=[
                [("propose_sql", {
                    "sql": "DROP TABLE customers",
                    "explanation": "Whoops.",
                })],
            ])

            client, _ = self._client(provider)
            async with client as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={
                    "prompt": "wreck things",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                # The agent loop terminated, but validation rejected.
                self.assertEqual(body["validation"]["ok"], False)
                self.assertIn("select", (body["validation"]["message"] or "").lower())

        _run(go())


class CapTests(_Base):
    def test_iteration_limit_aborts_cleanly(self):
        # 10 turns of pointless list_tables — agent never reaches propose_sql.
        async def go():
            provider = ScriptedToolProvider(script=[
                [("list_tables", {})] for _ in range(15)
            ])

            client, Session = self._client(provider)
            async with client as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={
                    "prompt": "go forever",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertFalse(body["succeeded"])
                self.assertEqual(body["error"], "iteration_limit")
                # Last step is an "abort" with a useful message.
                self.assertEqual(body["steps"][-1]["type"], "abort")
                self.assertIn("iteration limit", body["steps"][-1]["error"].lower())
                # Audit row records the failure.
                with Session() as db:
                    runs = db.query(KpiNlRun).all()
                    self.assertEqual(len(runs), 1)
                    self.assertFalse(runs[0].succeeded)
                    self.assertEqual(runs[0].error, "iteration_limit")

        _run(go())

    def test_token_budget_aborts_cleanly(self):
        # Each turn reports 100k tokens — first turn already busts the
        # 50k default budget.
        async def go():
            provider = ScriptedToolProvider(script=[
                {"calls": [("list_tables", {})], "usage": {"total_tokens": 100_000}},
                {"calls": [("propose_sql", {"sql": "SELECT 1", "explanation": "x"})], "usage": {"total_tokens": 1}},
            ])

            client, _ = self._client(provider)
            async with client as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={
                    "prompt": "huge",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertFalse(body["succeeded"])
                self.assertEqual(body["error"], "token_budget_exceeded")

        _run(go())


class TextOnlyTerminationTest(_Base):
    def test_text_only_response_terminates_with_thought_step(self):
        """When the model bails out on tool-use and just talks, treat
        the text as the final explanation and end the loop."""
        async def go():
            provider = ScriptedToolProvider(script=[
                "I cannot do that with the available schema.",
            ])

            client, _ = self._client(provider)
            async with client as c:
                r = await c.post("/api/v1/kpi/nl/generate", json={
                    "prompt": "something impossible",
                })
                self.assertEqual(r.status_code, 200, r.text)
                body = r.json()
                self.assertEqual(body["sql"], "")
                self.assertIn("schema", body["explanation"].lower())
                self.assertEqual(body["steps"][-1]["type"], "thought")

        _run(go())


if __name__ == "__main__":
    unittest.main()
