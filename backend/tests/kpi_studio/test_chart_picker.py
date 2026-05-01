"""Chart picker heuristic tests."""
from __future__ import annotations

import unittest

from kpi_studio.services.chart_picker import suggest_chart


class ScoreCardTests(unittest.TestCase):
    def test_single_row_single_number(self):
        s = suggest_chart(["total"], [[42]])
        self.assertEqual(s.type, "scorecard")
        self.assertEqual(s.config["value_column"], "total")

    def test_single_row_multiple_numbers_is_stat_group(self):
        s = suggest_chart(["a", "b", "c"], [[1, 2, 3]])
        self.assertEqual(s.type, "stat_group")
        self.assertEqual(s.config["value_columns"], ["a", "b", "c"])

    def test_single_row_no_numbers_is_table(self):
        s = suggest_chart(["status"], [["Approved"]])
        self.assertEqual(s.type, "table")


class TimeSeriesTests(unittest.TestCase):
    def test_iso_dates_with_numbers_is_line(self):
        s = suggest_chart(
            ["created_at", "amount"],
            [
                ["2026-01-01", 100],
                ["2026-02-01", 150],
                ["2026-03-01", 200],
            ],
        )
        self.assertEqual(s.type, "line")
        self.assertEqual(s.config["x_column"], "created_at")
        self.assertEqual(s.config["y_column"], "amount")

    def test_too_few_points_falls_back_to_bar(self):
        # Date column is fine but only 2 rows < LINE_MIN_POINTS=3.
        # Should pick bar (categorical breakdown) since row count is small.
        s = suggest_chart(
            ["month", "amount"],
            [
                ["2026-01-01", 100],
                ["2026-02-01", 150],
            ],
        )
        # We don't strictly require bar — just not line.
        self.assertNotEqual(s.type, "line")


class CategoricalTests(unittest.TestCase):
    def test_few_categories_with_numeric_is_bar(self):
        s = suggest_chart(
            ["region", "sales"],
            [
                ["North", 100],
                ["South", 200],
                ["East", 150],
                ["West", 175],
            ],
        )
        self.assertEqual(s.type, "bar")
        self.assertEqual(s.config["category_column"], "region")
        self.assertEqual(s.config["value_column"], "sales")
        self.assertIn("pie", s.alternates)

    def test_many_rows_falls_back_to_bar_not_pie(self):
        rows = [[f"Cat{i}", i] for i in range(20)]
        s = suggest_chart(["category", "count"], rows)
        self.assertEqual(s.type, "bar")
        self.assertNotIn("pie", s.alternates)


class FallbackTests(unittest.TestCase):
    def test_empty_result_is_table(self):
        s = suggest_chart(["a"], [])
        self.assertEqual(s.type, "table")

    def test_no_columns_is_table(self):
        s = suggest_chart([], [])
        self.assertEqual(s.type, "table")

    def test_purely_string_data_is_table(self):
        s = suggest_chart(
            ["a", "b"],
            [["x", "y"], ["p", "q"], ["m", "n"]],
        )
        self.assertEqual(s.type, "table")


if __name__ == "__main__":
    unittest.main()
