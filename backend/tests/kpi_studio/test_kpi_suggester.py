"""Tests for the Phase J KPI suggester.

A stubbed LLM provider returns canned JSON; the suggester service
parses it and validates each proposal through the spec compiler.
We verify happy-path acceptance, malformed-spec filtering, and
graceful degradation when the provider errors out.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError, LlmResult, LlmToolResult,
)
from kpi_studio.schemas import (
    ColumnInfo, ForeignKeyInfo, IndexInfo, SchemaPayload, TableInfo,
)
from kpi_studio.services import kpi_suggester


class _ScriptedProvider(LlmProvider):
    """LLM stub that returns a pre-canned text response. Captures the
    last messages array so tests can assert what the system / user
    prompts looked like."""
    name = "stub-suggester"

    def __init__(self, response_text: str = "{}", *, raise_error: str | None = None):
        self.response_text = response_text
        self.raise_error = raise_error
        self.last_messages: list[LlmMessage] = []

    def complete(self, messages, *, json_mode=False, max_tokens=None, temperature=0.2):
        self.last_messages = list(messages)
        if self.raise_error:
            raise LlmProviderError(self.raise_error)
        return LlmResult(
            text=self.response_text, model="stub-1", latency_ms=3,
            usage={"total_tokens": 42},
        )

    def complete_with_tools(self, *a, **kw):
        # Suggester only uses .complete(); fall back if invoked.
        return LlmToolResult(
            tool_calls=[], content=self.response_text,
            raw_assistant_message={"role": "assistant", "content": self.response_text},
            model="stub-1", latency_ms=3, usage={"total_tokens": 42},
        )


def _schema() -> SchemaPayload:
    """Tiny synthetic schema with one source table + one related."""
    enquiries = TableInfo(
        schema="dbo", name="enquiries",
        columns=[
            ColumnInfo(name="id",          type="INTEGER",  nullable=False, primary_key=True),
            ColumnInfo(name="customer_id", type="INTEGER",  nullable=False),
            ColumnInfo(name="region",      type="VARCHAR",  nullable=True),
            ColumnInfo(name="status",      type="VARCHAR",  nullable=True),
            ColumnInfo(name="amount",      type="DECIMAL",  nullable=True),
            ColumnInfo(name="created_at",  type="DATETIME", nullable=True),
        ],
        primary_key=["id"],
        foreign_keys=[ForeignKeyInfo(
            constrained_columns=["customer_id"],
            referred_table="customers",
            referred_columns=["id"],
        )],
        indexes=[IndexInfo(name="ix_status", columns=["status"], unique=False)],
    )
    customers = TableInfo(
        schema="dbo", name="customers",
        columns=[
            ColumnInfo(name="id",   type="INTEGER", nullable=False, primary_key=True),
            ColumnInfo(name="name", type="VARCHAR", nullable=False),
        ],
        primary_key=["id"],
    )
    return SchemaPayload(
        dialect="tsql",
        database_key="primary",
        introspected_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        tables=[enquiries, customers],
    )


def _good_proposal() -> dict:
    """A scorecard proposal that should compile cleanly."""
    return {
        "name": "Total enquiry value",
        "description": "Sum of every enquiry's amount.",
        "builder_spec": {
            "chart_type": "scorecard",
            "source": {"kind": "table", "schema": "dbo", "name": "enquiries"},
            "wells": {
                "value": [{"column": "amount", "agg": "SUM"}],
            },
            "filters": [],
            "top_n": None,
            "time_column": "created_at",
        },
    }


def _bad_proposal_missing_well() -> dict:
    """Missing the required ``axis`` well for a bar chart — should
    be filtered out by ``_validate_proposal`` via the compiler."""
    return {
        "name": "Broken bar",
        "description": "Bar chart without an axis.",
        "builder_spec": {
            "chart_type": "bar",
            "source": {"kind": "table", "schema": "dbo", "name": "enquiries"},
            "wells": {
                "values": [{"column": "amount", "agg": "SUM"}],
                # axis missing → compile should fail
            },
        },
    }


class SuggesterHappyPathTests(unittest.TestCase):
    def test_returns_validated_proposal(self):
        provider = _ScriptedProvider(json.dumps({
            "kpis": [_good_proposal()],
        }))
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="enquiries", table_schema="dbo", count=3,
        )
        self.assertEqual(len(result.items), 1)
        kpi = result.items[0]
        self.assertEqual(kpi.name, "Total enquiry value")
        self.assertEqual(kpi.builder_spec.chart_type, "scorecard")
        self.assertEqual(kpi.chart_config.type, "scorecard")
        self.assertIn("SUM([dbo].[enquiries].[amount])", kpi.sql)
        self.assertIsNone(result.error)
        self.assertEqual(result.tokens, 42)

    def test_drops_proposals_that_fail_to_compile(self):
        provider = _ScriptedProvider(json.dumps({
            "kpis": [_good_proposal(), _bad_proposal_missing_well()],
        }))
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="enquiries", table_schema="dbo",
        )
        # Only the good one survives; the broken bar chart is dropped.
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].name, "Total enquiry value")

    def test_accepts_bare_array_response(self):
        # Tolerate models that return [...] instead of { kpis: [...] }.
        provider = _ScriptedProvider(json.dumps([_good_proposal()]))
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="enquiries", table_schema="dbo",
        )
        self.assertEqual(len(result.items), 1)

    def test_strips_code_fence_wrap(self):
        # Some providers wrap JSON in ```json fences despite instructions.
        wrapped = "```json\n" + json.dumps({"kpis": [_good_proposal()]}) + "\n```"
        provider = _ScriptedProvider(wrapped)
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="enquiries", table_schema="dbo",
        )
        self.assertEqual(len(result.items), 1)


class SuggesterFailureTests(unittest.TestCase):
    def test_unknown_table_returns_error_no_provider_call(self):
        provider = _ScriptedProvider("{}")
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="missing_table",
        )
        self.assertEqual(result.items, [])
        self.assertIsNotNone(result.error)
        self.assertIn("missing_table", result.error)
        # Provider was never invoked.
        self.assertEqual(provider.last_messages, [])

    def test_provider_error_returns_empty_with_message(self):
        provider = _ScriptedProvider(raise_error="quota exceeded")
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="enquiries", table_schema="dbo",
        )
        self.assertEqual(result.items, [])
        self.assertIn("quota exceeded", result.error or "")

    def test_non_json_response_returns_parse_error(self):
        provider = _ScriptedProvider("here are some KPIs for you")
        result = kpi_suggester.suggest_kpis(
            provider=provider, schema=_schema(),
            table_name="enquiries", table_schema="dbo",
        )
        self.assertEqual(result.items, [])
        self.assertEqual(result.error, "parse_error")


if __name__ == "__main__":
    unittest.main()
