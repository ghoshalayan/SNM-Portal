"""Tests for ``services.spec_compiler`` — the Smart Builder spec → SQL
compiler that backs the Power BI–style drag-fields-into-wells editor.

We exercise:
  * each chart type's happy path (bar / pie / line / scorecard /
    stat_group / table)
  * filter rendering (scalar ops, ``in`` / ``not_in`` lists, ``between``
    ranges, ``is_null`` / ``is_not_null``)
  * time_column binding emits the standard ``:start_date`` /
    ``:end_date`` placeholders
  * structural validation errors (bad identifier, missing well,
    aggregation on raw well, illegal chart type)
"""
from __future__ import annotations

import unittest
from datetime import datetime

from kpi_studio.schemas import (
    AggregateFilter, BuilderField, BuilderFilter, BuilderSource, BuilderSpec,
    DerivedColumn,
)
from kpi_studio.services.spec_compiler import (
    SpecCompileError, compile_spec,
)


def _spec(**overrides):
    """Build a BuilderSpec with sensible defaults — tests override
    only the fields they care about."""
    base = {
        "chart_type": "bar",
        "source": BuilderSource(name="enquiries", schema="dbo"),
        "wells": {
            "axis":   [BuilderField(column="region")],
            "values": [BuilderField(column="amount", agg="SUM")],
        },
    }
    base.update(overrides)
    return BuilderSpec(**base)


class BarChartTests(unittest.TestCase):
    def test_basic_bar_groups_and_orders_by_value_desc(self):
        out = compile_spec(_spec())
        # Phase F — column refs are table-qualified so cross-table
        # joins resolve cleanly. Source columns get the source prefix.
        self.assertIn("[dbo].[enquiries].[region] AS [region]", out.sql)
        self.assertIn("SUM([dbo].[enquiries].[amount]) AS [amount_sum]", out.sql)
        self.assertIn("FROM [dbo].[enquiries]", out.sql)
        self.assertIn("GROUP BY [dbo].[enquiries].[region]", out.sql)
        # Default sort for bar: by aggregated value, descending.
        self.assertIn("ORDER BY SUM([dbo].[enquiries].[amount]) DESC", out.sql)
        self.assertEqual(out.chart_config.type, "bar")
        self.assertEqual(out.chart_config.config["category_column"], "region")
        self.assertEqual(out.chart_config.config["value_column"], "amount_sum")

    def test_bar_with_legend_groups_by_both(self):
        out = compile_spec(_spec(wells={
            "axis":   [BuilderField(column="region")],
            "values": [BuilderField(column="amount", agg="SUM")],
            "legend": [BuilderField(column="status")],
        }))
        self.assertIn("[dbo].[enquiries].[status] AS [status]", out.sql)
        self.assertIn("GROUP BY [dbo].[enquiries].[region], [dbo].[enquiries].[status]", out.sql)
        self.assertEqual(out.chart_config.config["legend_column"], "status")

    def test_top_n_emits_top_clause(self):
        out = compile_spec(_spec(top_n=10))
        self.assertIn("SELECT TOP 10", out.sql)


class PieAndLineTests(unittest.TestCase):
    def test_pie_uses_same_shape_as_bar(self):
        out = compile_spec(_spec(chart_type="pie"))
        self.assertEqual(out.chart_config.type, "pie")
        self.assertIn("GROUP BY [dbo].[enquiries].[region]", out.sql)

    def test_line_orders_by_axis_ascending(self):
        out = compile_spec(_spec(
            chart_type="line",
            wells={
                "axis":   [BuilderField(column="enq_date")],
                "values": [BuilderField(column="amount", agg="SUM")],
            },
        ))
        self.assertIn("ORDER BY [dbo].[enquiries].[enq_date] ASC", out.sql)
        self.assertEqual(out.chart_config.config["x_column"], "enq_date")
        self.assertEqual(out.chart_config.config["y_column"], "amount_sum")


class ScorecardTests(unittest.TestCase):
    def test_scorecard_emits_single_aggregate_no_group_by(self):
        out = compile_spec(_spec(
            chart_type="scorecard",
            wells={"value": [BuilderField(column="amount", agg="SUM")]},
        ))
        self.assertIn("SELECT SUM([dbo].[enquiries].[amount]) AS [amount_sum]", out.sql)
        self.assertNotIn("GROUP BY", out.sql)
        self.assertEqual(out.chart_config.type, "scorecard")
        self.assertEqual(out.chart_config.config["value_column"], "amount_sum")

    def test_scorecard_count_distinct_renders_correctly(self):
        out = compile_spec(_spec(
            chart_type="scorecard",
            wells={"value": [BuilderField(column="customer_id", agg="COUNT_DISTINCT")]},
        ))
        self.assertIn(
            "COUNT(DISTINCT [dbo].[enquiries].[customer_id]) AS [customer_id_distinct_count]",
            out.sql,
        )


class StatGroupTests(unittest.TestCase):
    def test_stat_group_emits_each_aggregate_with_independent_alias(self):
        out = compile_spec(_spec(
            chart_type="stat_group",
            wells={"values": [
                BuilderField(column="amount", agg="SUM"),
                BuilderField(column="quantity", agg="AVG", alias="avg_qty"),
                BuilderField(column="customer_id", agg="COUNT_DISTINCT"),
            ]},
        ))
        self.assertIn("SUM([dbo].[enquiries].[amount]) AS [amount_sum]", out.sql)
        self.assertIn("AVG([dbo].[enquiries].[quantity]) AS [avg_qty]", out.sql)
        self.assertIn("COUNT(DISTINCT [dbo].[enquiries].[customer_id])", out.sql)
        self.assertEqual(
            out.chart_config.config["value_columns"],
            ["amount_sum", "avg_qty", "customer_id_distinct_count"],
        )


class TableTests(unittest.TestCase):
    def test_table_lists_columns_no_group_by(self):
        out = compile_spec(_spec(
            chart_type="table",
            wells={"columns": [
                BuilderField(column="enquiry_no"),
                BuilderField(column="customer_name", sort="asc"),
                BuilderField(column="amount"),
            ]},
        ))
        self.assertIn("[dbo].[enquiries].[enquiry_no] AS [enquiry_no]", out.sql)
        self.assertIn("[dbo].[enquiries].[customer_name] AS [customer_name]", out.sql)
        self.assertNotIn("GROUP BY", out.sql)
        self.assertIn("ORDER BY [dbo].[enquiries].[customer_name] ASC", out.sql)

    def test_table_rejects_aggregated_field(self):
        with self.assertRaises(SpecCompileError) as ctx:
            compile_spec(_spec(
                chart_type="table",
                wells={"columns": [BuilderField(column="amount", agg="SUM")]},
            ))
        self.assertIn("aggregated", str(ctx.exception).lower())


class FilterTests(unittest.TestCase):
    def test_scalar_equality_with_string(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="status", op="=", value="Open"),
        ]))
        self.assertIn("WHERE [dbo].[enquiries].[status] = N'Open'", out.sql)

    def test_string_with_single_quote_is_escaped(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="customer_name", op="=", value="O'Reilly"),
        ]))
        # Single quotes inside literals are doubled-up in T-SQL.
        self.assertIn("N'O''Reilly'", out.sql)

    def test_in_list_emits_parenthesised_csv(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="region", op="in", value=["North", "South"]),
        ]))
        self.assertIn("[dbo].[enquiries].[region] IN (N'North', N'South')", out.sql)

    def test_in_with_empty_list_rejected(self):
        with self.assertRaises(SpecCompileError):
            compile_spec(_spec(filters=[
                BuilderFilter(column="region", op="in", value=[]),
            ]))

    def test_between_with_dates(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(
                column="enq_date", op="between",
                value=[datetime(2026, 1, 1), datetime(2026, 3, 31)],
            ),
        ]))
        self.assertIn("[dbo].[enquiries].[enq_date] BETWEEN N'2026-01-01T00:00:00' AND N'2026-03-31T00:00:00'", out.sql)

    def test_is_null_emits_bare_predicate(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="closed_at", op="is_null"),
        ]))
        self.assertIn("[dbo].[enquiries].[closed_at] IS NULL", out.sql)

    def test_numeric_filter_does_not_quote(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="amount", op=">=", value=10000),
        ]))
        self.assertIn("[dbo].[enquiries].[amount] >= 10000", out.sql)
        self.assertNotIn("N'10000'", out.sql)


class TimeBindingTests(unittest.TestCase):
    def test_time_column_injects_period_placeholders(self):
        out = compile_spec(_spec(time_column="enq_date"))
        self.assertIn("[dbo].[enquiries].[enq_date] BETWEEN :start_date AND :end_date", out.sql)


class ValidationTests(unittest.TestCase):
    def test_invalid_identifier_rejected(self):
        with self.assertRaises(SpecCompileError):
            compile_spec(_spec(wells={
                "axis":   [BuilderField(column="region; DROP TABLE x")],
                "values": [BuilderField(column="amount", agg="SUM")],
            }))

    def test_missing_required_well_rejected(self):
        with self.assertRaises(SpecCompileError) as ctx:
            compile_spec(_spec(wells={
                "axis": [BuilderField(column="region")],
                # 'values' missing
            }))
        self.assertIn("values", str(ctx.exception))

    def test_unknown_well_rejected(self):
        with self.assertRaises(SpecCompileError):
            compile_spec(_spec(wells={
                "axis":     [BuilderField(column="region")],
                "values":   [BuilderField(column="amount", agg="SUM")],
                "category": [BuilderField(column="x")],  # not a thing
            }))

    def test_value_field_without_aggregation_rejected(self):
        with self.assertRaises(SpecCompileError) as ctx:
            compile_spec(_spec(wells={
                "axis":   [BuilderField(column="region")],
                "values": [BuilderField(column="amount")],  # no agg
            }))
        self.assertIn("aggregation", str(ctx.exception).lower())

    def test_axis_field_with_aggregation_rejected(self):
        with self.assertRaises(SpecCompileError):
            compile_spec(_spec(wells={
                "axis":   [BuilderField(column="region", agg="SUM")],
                "values": [BuilderField(column="amount", agg="SUM")],
            }))


class _Edge:
    """Tiny stand-in for KpiTableRelationship — duck-types just enough
    for the compiler's join-path walker. Lets these tests stay
    independent of the SQLAlchemy schema."""
    def __init__(self, ft, fc, tt, tc, fs=None, ts=None, active=True):
        self.from_schema = fs
        self.from_table = ft
        self.from_column = fc
        self.to_schema = ts
        self.to_table = tt
        self.to_column = tc
        self.is_active = active


class JoinTests(unittest.TestCase):
    """Phase F — cross-table compile path. A BuilderField with a
    ``table`` different from the source triggers a relationship-graph
    walk; the compiler emits the ``LEFT JOIN`` chain automatically."""

    def test_field_on_related_table_emits_left_join(self):
        # enquiries (source) → customers (related, via customer_id FK).
        # The default ``_spec()`` source carries schema=dbo, so the
        # edges need matching schema to stay in the same graph node.
        rels = [_Edge("enquiries", "customer_id", "customers", "id", fs="dbo", ts="dbo")]
        spec = _spec(wells={
            "axis":   [BuilderField(column="name", table="customers", schema="dbo")],
            "values": [BuilderField(column="amount", agg="SUM")],
        })
        out = compile_spec(spec, relationships=rels)
        self.assertIn("LEFT JOIN [dbo].[customers] ON", out.sql)
        self.assertIn("[dbo].[enquiries].[customer_id] = [dbo].[customers].[id]", out.sql)
        # Axis column referenced via the related table.
        self.assertIn("[dbo].[customers].[name] AS [name]", out.sql)
        # Aggregated source column stays on the source.
        self.assertIn("SUM([dbo].[enquiries].[amount])", out.sql)

    def test_two_hop_path_emits_chained_joins(self):
        # enquiries → customers → companies
        rels = [
            _Edge("enquiries", "customer_id", "customers", "id", fs="dbo", ts="dbo"),
            _Edge("customers", "company_id", "companies", "id", fs="dbo", ts="dbo"),
        ]
        spec = _spec(wells={
            "axis":   [BuilderField(column="name", table="companies", schema="dbo")],
            "values": [BuilderField(column="amount", agg="SUM")],
        })
        out = compile_spec(spec, relationships=rels)
        # Both join clauses should be present, in path order.
        self.assertIn("LEFT JOIN [dbo].[customers]", out.sql)
        self.assertIn("LEFT JOIN [dbo].[companies]", out.sql)
        self.assertIn("[dbo].[customers].[company_id] = [dbo].[companies].[id]", out.sql)

    def test_unrelated_table_rejected_with_helpful_error(self):
        # enquiries (source) and warehouses (no edge) — compile fails.
        rels = [_Edge("enquiries", "customer_id", "customers", "id", fs="dbo", ts="dbo")]
        with self.assertRaises(SpecCompileError) as ctx:
            compile_spec(_spec(wells={
                "axis":   [BuilderField(column="zone", table="warehouses", schema="dbo")],
                "values": [BuilderField(column="amount", agg="SUM")],
            }), relationships=rels)
        msg = str(ctx.exception).lower()
        self.assertIn("relationship", msg)
        self.assertIn("warehouses", msg)

    def test_inactive_edge_is_ignored(self):
        rels = [
            _Edge("enquiries", "customer_id", "customers", "id",
                  fs="dbo", ts="dbo", active=False),
        ]
        with self.assertRaises(SpecCompileError):
            compile_spec(_spec(wells={
                "axis":   [BuilderField(column="name", table="customers", schema="dbo")],
                "values": [BuilderField(column="amount", agg="SUM")],
            }), relationships=rels)

    def test_table_ref_to_source_table_does_not_double_join(self):
        # Authors sometimes set ``table`` to the source explicitly. The
        # compiler should detect that and skip the join lookup.
        spec = _spec(wells={
            "axis":   [BuilderField(column="region", table="enquiries")],
            "values": [BuilderField(column="amount", agg="SUM")],
        })
        out = compile_spec(spec, relationships=[])
        self.assertNotIn("LEFT JOIN", out.sql)


class DerivedColumnTests(unittest.TestCase):
    """Phase G — calculated columns. The compiler wraps the source
    in a CTE so each expression evaluates once per row, and downstream
    references resolve against the alias just like a real column."""

    def test_arithmetic_derived_column_in_aggregate(self):
        out = compile_spec(_spec(
            wells={
                "axis":   [BuilderField(column="region")],
                # Reference the derived column by alias as if it were
                # a real source column.
                "values": [BuilderField(column="amount_with_gst", agg="SUM")],
            },
            derived_columns=[
                DerivedColumn(alias="amount_with_gst", expression="amount * 1.18"),
            ],
        ))
        # CTE prefix wraps the source.
        self.assertIn("WITH [__src] AS (", out.sql)
        self.assertIn("(amount * 1.18) AS [amount_with_gst]", out.sql)
        self.assertIn("FROM [dbo].[enquiries]", out.sql)
        # Main query references the CTE.
        self.assertIn("FROM [__src]", out.sql)
        # Source-column refs qualify via the CTE alias.
        self.assertIn("[__src].[region]", out.sql)
        # Derived column referenced through the CTE too.
        self.assertIn("SUM([__src].[amount_with_gst])", out.sql)

    def test_case_when_derived_column(self):
        out = compile_spec(_spec(
            chart_type="scorecard",
            wells={"value": [BuilderField(column="open_count", agg="SUM")]},
            derived_columns=[
                DerivedColumn(
                    alias="open_count",
                    expression="CASE WHEN status = 'Open' THEN 1 ELSE 0 END",
                ),
            ],
        ))
        self.assertIn("CASE WHEN status = 'Open' THEN 1 ELSE 0 END", out.sql)
        self.assertIn("AS [open_count]", out.sql)
        self.assertIn("SUM([__src].[open_count])", out.sql)

    def test_derived_column_usable_in_filter(self):
        out = compile_spec(_spec(
            filters=[BuilderFilter(column="is_open", op="=", value=1)],
            derived_columns=[
                DerivedColumn(
                    alias="is_open",
                    expression="CASE WHEN status = 'Open' THEN 1 ELSE 0 END",
                ),
            ],
        ))
        self.assertIn("WHERE [__src].[is_open] = 1", out.sql)

    def test_no_cte_when_no_derived_columns(self):
        # Sanity: empty derived list = old behaviour, no CTE wrap.
        out = compile_spec(_spec(derived_columns=[]))
        self.assertNotIn("WITH ", out.sql)
        self.assertNotIn("[__src]", out.sql)
        self.assertIn("FROM [dbo].[enquiries]", out.sql)

    def test_duplicate_alias_rejected(self):
        with self.assertRaises(SpecCompileError):
            compile_spec(_spec(derived_columns=[
                DerivedColumn(alias="x", expression="1"),
                DerivedColumn(alias="x", expression="2"),
            ]))

    def test_semicolon_in_expression_rejected(self):
        with self.assertRaises(SpecCompileError) as ctx:
            compile_spec(_spec(derived_columns=[
                DerivedColumn(alias="bad", expression="1; DROP TABLE x"),
            ]))
        self.assertIn("semicolon", str(ctx.exception).lower())

    def test_join_works_with_derived_columns(self):
        # Derived column on the source CTE PLUS a join into a related
        # table — joined columns still go via the physical table.
        rels = [_Edge("enquiries", "customer_id", "customers", "id",
                      fs="dbo", ts="dbo")]
        out = compile_spec(
            _spec(
                wells={
                    "axis":   [BuilderField(column="name", table="customers", schema="dbo")],
                    "values": [BuilderField(column="amount_with_gst", agg="SUM")],
                },
                derived_columns=[
                    DerivedColumn(alias="amount_with_gst", expression="amount * 1.18"),
                ],
            ),
            relationships=rels,
        )
        # Source side of the JOIN should use the CTE alias.
        self.assertIn("[__src].[customer_id] = [dbo].[customers].[id]", out.sql)
        # Joined column stays on the physical table.
        self.assertIn("[dbo].[customers].[name] AS [name]", out.sql)
        # Derived column still computed in the CTE and used in SUM.
        self.assertIn("(amount * 1.18) AS [amount_with_gst]", out.sql)
        self.assertIn("SUM([__src].[amount_with_gst])", out.sql)


class AggregateFilterTests(unittest.TestCase):
    """Phase G.2 — HAVING clause. Filters predicate on aggregated
    values (post-GROUP BY) so the user can keep only categories whose
    SUM/COUNT/AVG meets a threshold."""

    def test_basic_having_emits_after_group_by(self):
        out = compile_spec(_spec(aggregate_filters=[
            AggregateFilter(column="amount", agg="SUM", op=">", value=100000),
        ]))
        # GROUP BY comes from the bar chart axis; HAVING follows it.
        self.assertIn("GROUP BY [dbo].[enquiries].[region]", out.sql)
        self.assertIn("HAVING SUM([dbo].[enquiries].[amount]) > 100000", out.sql)

    def test_count_distinct_having(self):
        out = compile_spec(_spec(aggregate_filters=[
            AggregateFilter(
                column="customer_id", agg="COUNT_DISTINCT",
                op=">=", value=5,
            ),
        ]))
        self.assertIn("HAVING COUNT(DISTINCT [dbo].[enquiries].[customer_id]) >= 5", out.sql)

    def test_having_between_two_values(self):
        out = compile_spec(_spec(aggregate_filters=[
            AggregateFilter(column="amount", agg="SUM", op="between", value=[10000, 50000]),
        ]))
        self.assertIn("HAVING SUM([dbo].[enquiries].[amount]) BETWEEN 10000 AND 50000", out.sql)

    def test_having_after_where_after_group_by_after_join(self):
        # All four clauses present and in correct SQL order.
        out = compile_spec(_spec(
            filters=[BuilderFilter(column="status", op="=", value="Open")],
            aggregate_filters=[
                AggregateFilter(column="amount", agg="SUM", op=">", value=1000),
            ],
        ))
        # Verify the order via positional checks.
        sql = out.sql
        i_from = sql.index("FROM ")
        i_where = sql.index("WHERE ")
        i_group = sql.index("GROUP BY ")
        i_having = sql.index("HAVING ")
        i_order = sql.index("ORDER BY ")
        self.assertLess(i_from, i_where)
        self.assertLess(i_where, i_group)
        self.assertLess(i_group, i_having)
        self.assertLess(i_having, i_order)


class RuntimeParamTests(unittest.TestCase):
    """Phase I — filter values can reference runtime-bound parameters
    (:company_id / :user_id / :start_date / :end_date) instead of
    inlined literals, so a single KPI auto-slices per caller."""

    def test_company_id_param_ref_compiles_to_bind_marker(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="company_id", op="=", value={"$param": "company_id"}),
        ]))
        self.assertIn("WHERE [dbo].[enquiries].[company_id] = :company_id", out.sql)
        # Crucially: not inlined as a literal.
        self.assertNotIn("N'", out.sql.split("WHERE")[1])

    def test_user_id_param_ref(self):
        out = compile_spec(_spec(filters=[
            BuilderFilter(column="owner_user_id", op="=", value={"$param": "user_id"}),
        ]))
        self.assertIn("[owner_user_id] = :user_id", out.sql)

    def test_param_ref_in_aggregate_filter(self):
        out = compile_spec(_spec(aggregate_filters=[
            AggregateFilter(column="company_id", agg="COUNT_DISTINCT",
                            op=">", value={"$param": "user_id"}),
        ]))
        # HAVING side also accepts param refs (rare but supported).
        self.assertIn(":user_id", out.sql.split("HAVING")[1])

    def test_unknown_param_rejected(self):
        with self.assertRaises(SpecCompileError) as ctx:
            compile_spec(_spec(filters=[
                BuilderFilter(column="x", op="=", value={"$param": "secret_key"}),
            ]))
        self.assertIn("secret_key", str(ctx.exception))

    def test_param_ref_inside_in_list(self):
        # Mixed list: literal + param ref.
        out = compile_spec(_spec(filters=[
            BuilderFilter(
                column="visible_id", op="in",
                value=[{"$param": "user_id"}, {"$param": "company_id"}],
            ),
        ]))
        self.assertIn("[visible_id] IN (:user_id, :company_id)", out.sql)


if __name__ == "__main__":
    unittest.main()
