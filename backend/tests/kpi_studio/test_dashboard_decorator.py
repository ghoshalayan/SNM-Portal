"""Tests for the Phase J.2 dashboard decorator.

The service takes a dashboard's items + their KPI chart types and asks
an LLM for a tidier layout. Each placement is validated (item ids
must exist, coords must fit the 24-col grid) and overlapping tiles
are pushed down. When the LLM fails, a rule-based packer takes over
so the caller always gets a usable layout.
"""
from __future__ import annotations

import json
import unittest
from typing import List

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError, LlmResult, LlmToolResult,
)
from kpi_studio.schemas import BuilderField, BuilderFilter, BuilderSource, BuilderSpec
from kpi_studio.services import dashboard_decorator
from kpi_studio.services.dashboard_decorator import DashboardItemView


class _ScriptedProvider(LlmProvider):
    name = "stub-decorator"

    def __init__(self, response_text: str = "{}", *, raise_error: str | None = None):
        self.response_text = response_text
        self.raise_error = raise_error
        self.last_messages: list[LlmMessage] = []

    def complete(self, messages, *, json_mode=False, max_tokens=None, temperature=0.2):
        self.last_messages = list(messages)
        if self.raise_error:
            raise LlmProviderError(self.raise_error)
        return LlmResult(
            text=self.response_text, model="stub-1", latency_ms=2,
            usage={"total_tokens": 17},
        )

    def complete_with_tools(self, *a, **kw):
        return LlmToolResult(
            tool_calls=[], content=self.response_text,
            raw_assistant_message={"role": "assistant", "content": self.response_text},
            model="stub-1", latency_ms=2, usage={"total_tokens": 17},
        )


def _items() -> List[DashboardItemView]:
    """Three-card dashboard: a scorecard, a bar chart, and a table."""
    return [
        DashboardItemView(
            item_id=1, kpi_id=10, kpi_name="Total Sales",
            chart_type="scorecard",
            grid_x=0, grid_y=0, grid_w=12, grid_h=8,
            size_class="md", title_override=None,
        ),
        DashboardItemView(
            item_id=2, kpi_id=11, kpi_name="Sales by Region",
            chart_type="bar",
            grid_x=12, grid_y=0, grid_w=12, grid_h=8,
            size_class="md", title_override=None,
        ),
        DashboardItemView(
            item_id=3, kpi_id=12, kpi_name="Recent Orders",
            chart_type="table",
            grid_x=0, grid_y=8, grid_w=24, grid_h=10,
            size_class="wide", title_override=None,
        ),
    ]


class DecoratorHappyPathTests(unittest.TestCase):
    def test_returns_validated_placements(self):
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm", "title_override": "Sales"},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md", "title_override": None},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide", "title_override": None},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(), dashboard_name="Sales overview",
        )
        self.assertFalse(result.used_fallback)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.items), 3)
        scorecard = next(p for p in result.items if p.item_id == 1)
        # AI Polish never changes layout — even if the LLM proposed
        # a smaller size, the original size_class is preserved.
        self.assertEqual(scorecard.size_class, "md")
        self.assertEqual(scorecard.grid_x, 0)
        self.assertEqual(scorecard.grid_y, 0)
        self.assertEqual(scorecard.grid_w, 12)
        self.assertEqual(scorecard.grid_h, 8)
        # Polish fields ARE applied — title override gets through.
        self.assertEqual(scorecard.title_override, "Sales")
        self.assertEqual(result.tokens, 17)

    def test_accepts_bare_array_response(self):
        provider = _ScriptedProvider(json.dumps([
            {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
             "size_class": "sm"},
            {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
             "size_class": "md"},
            {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
             "size_class": "wide"},
        ]))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(),
        )
        self.assertEqual(len(result.items), 3)
        self.assertFalse(result.used_fallback)

    def test_strips_code_fence_wrap(self):
        wrapped = "```json\n" + json.dumps({"items": [
            {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
             "size_class": "sm"},
            {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
             "size_class": "md"},
            {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
             "size_class": "wide"},
        ]}) + "\n```"
        provider = _ScriptedProvider(wrapped)
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(),
        )
        self.assertFalse(result.used_fallback)
        self.assertEqual(len(result.items), 3)


class DecoratorValidationTests(unittest.TestCase):
    def test_drops_unknown_item_ids(self):
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm"},
                {"item_id": 999, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(),
        )
        ids = {p.item_id for p in result.items}
        self.assertNotIn(999, ids)
        # Missing items (2, 3) get backfilled by the rule-based packer.
        self.assertEqual(ids, {1, 2, 3})

    def test_ignores_llm_layout_proposals(self):
        # Even when the LLM emits wildly different (or invalid) coords,
        # AI Polish discards them and preserves the user's manual
        # layout. The polish-only contract is enforced server-side
        # regardless of what the model returned.
        items = _items()
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 99, "grid_y": -5, "grid_w": 99, "grid_h": 200,
                 "size_class": "sm"},
                {"item_id": 2, "grid_x": 0, "grid_y": 0, "grid_w": 4, "grid_h": 2,
                 "size_class": "sm"},
                {"item_id": 3, "grid_x": 6, "grid_y": 50, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        by_id = {p.item_id: p for p in result.items}
        for it in items:
            p = by_id[it.item_id]
            self.assertEqual(
                (p.grid_x, p.grid_y, p.grid_w, p.grid_h),
                (it.grid_x, it.grid_y, it.grid_w, it.grid_h),
                f"item {it.item_id} layout was modified",
            )
            self.assertEqual(p.size_class, it.size_class)

    def test_layout_stays_pinned_even_when_llm_overlaps_proposals(self):
        # Two LLM proposals claim the same rectangle — under the old
        # "Arrange" contract this would have been resolved by pushing
        # one down. Under "Polish" we just discard both and use the
        # user's original (non-overlapping) layout.
        items = _items()
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 12, "grid_h": 4,
                 "size_class": "md"},
                {"item_id": 2, "grid_x": 0, "grid_y": 0, "grid_w": 12, "grid_h": 4,
                 "size_class": "md"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        # Verify no two placements overlap (because they all kept the
        # user's original non-overlapping coords).
        for i, a in enumerate(result.items):
            for b in result.items[i+1:]:
                ax, ay, aw, ah = a.grid_x, a.grid_y, a.grid_w, a.grid_h
                bx, by, bw, bh = b.grid_x, b.grid_y, b.grid_w, b.grid_h
                overlap = not (
                    ax + aw <= bx or bx + bw <= ax
                    or ay + ah <= by or by + bh <= ay
                )
                self.assertFalse(overlap, f"items {a.item_id} and {b.item_id} overlap")

    def test_unknown_size_class_falls_back_to_original(self):
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "GIANT"},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(),
        )
        first = next(p for p in result.items if p.item_id == 1)
        # Original size_class for item 1 was "md" — kept when LLM
        # supplied a bogus value.
        self.assertEqual(first.size_class, "md")


class DecoratorFallbackTests(unittest.TestCase):
    def test_provider_error_falls_back_to_rule_based_pack(self):
        provider = _ScriptedProvider(raise_error="quota exceeded")
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(),
        )
        self.assertTrue(result.used_fallback)
        self.assertIn("quota exceeded", result.error or "")
        # Every input item appears in the fallback layout.
        self.assertEqual(len(result.items), 3)
        self.assertEqual({p.item_id for p in result.items}, {1, 2, 3})

    def test_non_json_response_falls_back(self):
        provider = _ScriptedProvider("here's a layout I guess")
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items(),
        )
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.error, "parse_error")
        self.assertEqual(len(result.items), 3)

    def test_fallback_preserves_layout_unchanged(self):
        # AI Polish never moves cards — even on the LLM-fallback path.
        # The packer just emits identity placements that mirror each
        # input view's grid coords + size_class exactly.
        items = _items()
        placements = dashboard_decorator._fallback_pack(items)
        by_id = {p.item_id: p for p in placements}
        for it in items:
            p = by_id[it.item_id]
            self.assertEqual((p.grid_x, p.grid_y, p.grid_w, p.grid_h),
                             (it.grid_x, it.grid_y, it.grid_w, it.grid_h))
            self.assertEqual(p.size_class, it.size_class)

    def test_empty_dashboard_is_a_noop(self):
        provider = _ScriptedProvider("{}")
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=[],
        )
        self.assertEqual(result.items, [])
        self.assertFalse(result.used_fallback)
        # Provider was never invoked.
        self.assertEqual(provider.last_messages, [])


def _spec_with_columns(table: str, cols: list[str]) -> BuilderSpec:
    """Build a tiny BuilderSpec whose ``axis``/``value`` wells reference
    the named columns — used to give the decorator a real
    ``filterable_columns`` set."""
    fields = [BuilderField(column=c) for c in cols]
    return BuilderSpec(
        chart_type="bar",
        source=BuilderSource(kind="table", schema_name="dbo", name=table),
        wells={"axis": [fields[0]], "values": [fields[1]] if len(fields) > 1 else []},
        filters=[],
    )


def _items_with_specs() -> list[DashboardItemView]:
    """Three-card dashboard, items 1 and 2 carry a BuilderSpec so the
    decorator can validate filter proposals against real columns. Item
    3 has no spec (raw-SQL KPI) — the decorator should still place it
    but skip filter induction."""
    spec_1 = _spec_with_columns("enquiries", ["amount"])
    spec_2 = _spec_with_columns("enquiries", ["region", "amount"])
    return [
        DashboardItemView(
            item_id=1, kpi_id=10, kpi_name="Total Sales",
            chart_type="scorecard",
            grid_x=0, grid_y=0, grid_w=12, grid_h=8,
            size_class="md", builder_spec=spec_1,
        ),
        DashboardItemView(
            item_id=2, kpi_id=11, kpi_name="Sales by Region",
            chart_type="bar",
            grid_x=12, grid_y=0, grid_w=12, grid_h=8,
            size_class="md", builder_spec=spec_2,
        ),
        DashboardItemView(
            item_id=3, kpi_id=12, kpi_name="Recent Orders",
            chart_type="table",
            grid_x=0, grid_y=8, grid_w=24, grid_h=10,
            size_class="wide", builder_spec=None,
        ),
    ]


class DecoratorPolishTests(unittest.TestCase):
    """Phase J.2 polish — icon, animations, and filter induction."""

    def test_accepts_icon_animations_filters(self):
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm", "icon": "trending_up",
                 "animation_in": "fade", "animation_out": "fade",
                 "extra_filters": [{"column": "amount", "op": ">", "value": 0}]},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md", "icon": "bar_chart",
                 "animation_in": "slide", "animation_out": "fade",
                 "extra_filters": [{"column": "region", "op": "=", "value": "North"}]},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide", "icon": "table_chart",
                 "animation_in": "slide", "animation_out": "scale"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items_with_specs(),
        )
        self.assertFalse(result.used_fallback)
        first = next(p for p in result.items if p.item_id == 1)
        self.assertEqual(first.icon, "trending_up")
        self.assertEqual(first.animation_in, "fade")
        self.assertEqual(len(first.extra_filters), 1)
        self.assertEqual(first.extra_filters[0].column, "amount")

    def test_drops_fabricated_filter_columns(self):
        # Item 1's spec only knows about ``amount``, so a filter
        # against ``customer_name`` should be dropped.
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm",
                 "extra_filters": [
                     {"column": "amount", "op": ">", "value": 0},
                     {"column": "customer_name", "op": "=", "value": "X"},
                 ]},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items_with_specs(),
        )
        first = next(p for p in result.items if p.item_id == 1)
        cols = {f.column for f in first.extra_filters}
        self.assertEqual(cols, {"amount"})

    def test_rejects_unknown_icon_keeps_original(self):
        # Item 1 starts with no icon; item 2 starts with one already.
        items = _items_with_specs()
        items[1].icon = "show_chart"  # original
        provider = _ScriptedProvider(json.dumps({
            "items": [
                # Bogus icon name — should fall back to "no icon".
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm", "icon": "magic_unicorn"},
                # Bogus icon — should keep the original "show_chart".
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md", "icon": "made_up_icon"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        first = next(p for p in result.items if p.item_id == 1)
        second = next(p for p in result.items if p.item_id == 2)
        self.assertIsNone(first.icon)
        self.assertEqual(second.icon, "show_chart")

    def test_unknown_animation_keeps_original(self):
        items = _items_with_specs()
        items[0].animation_in = "fade"
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm", "animation_in": "WOBBLE"},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        first = next(p for p in result.items if p.item_id == 1)
        # Unknown animation falls back to original ("fade").
        self.assertEqual(first.animation_in, "fade")

    def test_filter_induction_skipped_for_raw_sql_kpi(self):
        # Item 3 has no builder_spec — even if the LLM proposes
        # a filter, validation accepts it (no allow-list to check
        # against). But if there are no filterable_columns provided
        # to the prompt, well-behaved models won't propose any. We
        # simulate the common case: extra_filters omitted.
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm"},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items_with_specs(),
        )
        third = next(p for p in result.items if p.item_id == 3)
        self.assertEqual(third.extra_filters, [])

    def test_caps_filters_at_three_per_card(self):
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "grid_x": 0, "grid_y": 0, "grid_w": 6, "grid_h": 4,
                 "size_class": "sm",
                 "extra_filters": [
                     {"column": "amount", "op": ">", "value": 1},
                     {"column": "amount", "op": "<", "value": 100},
                     {"column": "amount", "op": "!=", "value": 50},
                     {"column": "amount", "op": ">", "value": 0},  # 4th — dropped
                     {"column": "amount", "op": ">", "value": 2},  # 5th — dropped
                 ]},
                {"item_id": 2, "grid_x": 6, "grid_y": 0, "grid_w": 12, "grid_h": 8,
                 "size_class": "md"},
                {"item_id": 3, "grid_x": 0, "grid_y": 8, "grid_w": 24, "grid_h": 10,
                 "size_class": "wide"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items_with_specs(),
        )
        first = next(p for p in result.items if p.item_id == 1)
        self.assertEqual(len(first.extra_filters), 3)

    def test_accepts_axis_labels_for_bar_and_line(self):
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "x_label": "X", "y_label": "Y"},  # scorecard — ignored
                {"item_id": 2, "x_label": "Region", "y_label": "Sales (₹)"},
                {"item_id": 3, "x_label": "Cust", "y_label": "Date"},  # table — ignored
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items_with_specs(),
        )
        # Bar chart accepts axis labels.
        bar = next(p for p in result.items if p.item_id == 2)
        self.assertEqual(bar.x_label, "Region")
        self.assertEqual(bar.y_label, "Sales (₹)")
        # Scorecard / table ignore axis labels — they don't render them.
        scorecard = next(p for p in result.items if p.item_id == 1)
        self.assertIsNone(scorecard.x_label)
        self.assertIsNone(scorecard.y_label)
        table = next(p for p in result.items if p.item_id == 3)
        self.assertIsNone(table.x_label)
        self.assertIsNone(table.y_label)

    def test_axis_labels_trim_long_values(self):
        # Anything past 30 chars gets truncated rather than rejected —
        # losing the tail beats losing the whole label.
        long = "A very verbose axis label that nobody wants to read"
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1},
                {"item_id": 2, "x_label": long, "y_label": long},
                {"item_id": 3},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=_items_with_specs(),
        )
        bar = next(p for p in result.items if p.item_id == 2)
        self.assertEqual(len(bar.x_label or ""), 30)
        self.assertTrue(long.startswith(bar.x_label or ""))

    def test_axis_labels_empty_string_clears_override(self):
        # Item 2 starts with axis labels set; the LLM proposes "" which
        # should clear them rather than treat as "no change".
        items = _items_with_specs()
        items[1].x_label = "Old X"
        items[1].y_label = "Old Y"
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1},
                {"item_id": 2, "x_label": "", "y_label": ""},
                {"item_id": 3},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        bar = next(p for p in result.items if p.item_id == 2)
        self.assertIsNone(bar.x_label)
        self.assertIsNone(bar.y_label)

    def test_axis_labels_omitted_keeps_original(self):
        items = _items_with_specs()
        items[1].x_label = "Region"
        items[1].y_label = "Sales"
        # Proposal omits x_label / y_label entirely → keep originals.
        provider = _ScriptedProvider(json.dumps({
            "items": [
                {"item_id": 1, "icon": "trending_up"},
                {"item_id": 2, "icon": "bar_chart"},
                {"item_id": 3, "icon": "table_chart"},
            ],
        }))
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        bar = next(p for p in result.items if p.item_id == 2)
        self.assertEqual(bar.x_label, "Region")
        self.assertEqual(bar.y_label, "Sales")

    def test_fallback_packer_preserves_existing_polish(self):
        items = _items_with_specs()
        items[0].icon = "trending_up"
        items[0].animation_in = "fade"
        items[0].extra_filters = [BuilderFilter(column="amount", op=">", value=0)]
        # Force the fallback path by feeding a non-JSON response.
        provider = _ScriptedProvider("nope")
        result = dashboard_decorator.decorate_dashboard(
            provider=provider, items=items,
        )
        self.assertTrue(result.used_fallback)
        first = next(p for p in result.items if p.item_id == 1)
        self.assertEqual(first.icon, "trending_up")
        self.assertEqual(first.animation_in, "fade")
        self.assertEqual(len(first.extra_filters), 1)


if __name__ == "__main__":
    unittest.main()
