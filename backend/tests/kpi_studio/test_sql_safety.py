"""SQL safety validator tests.

Coverage focus:
  * SELECT-only enforcement
  * Banned tokens / functions
  * System schema rejection
  * Multi-statement rejection
  * TOP/LIMIT injection + clamping
  * CTE acceptance
"""
from __future__ import annotations

import unittest

from kpi_studio.services.sql_safety import (
    SqlSafetyError, validate_select_query,
)


class AcceptedQueriesTests(unittest.TestCase):
    def test_plain_select_gets_top_injected(self):
        q = validate_select_query("SELECT 1")
        self.assertIn("TOP 50000", q.rewritten)
        self.assertEqual(q.row_cap, 50_000)
        self.assertTrue(any("Injected" in n for n in q.notes))

    def test_select_from_real_table(self):
        q = validate_select_query("select * from QuotSummary where companyId = 1")
        self.assertIn("TOP 50000", q.rewritten)
        self.assertIn("QuotSummary", q.rewritten)

    def test_existing_top_under_cap_is_left_alone(self):
        q = validate_select_query("SELECT TOP 10 * FROM QuotSummary")
        self.assertIn("TOP 10", q.rewritten)
        self.assertNotIn("TOP 50000", q.rewritten)
        self.assertEqual(q.row_cap, 10)

    def test_existing_top_above_cap_is_clamped(self):
        q = validate_select_query("SELECT TOP 999999 * FROM QuotSummary", row_cap=100)
        self.assertIn("TOP 100", q.rewritten)
        self.assertNotIn("999999", q.rewritten)
        self.assertEqual(q.row_cap, 100)
        self.assertTrue(any("Lowered" in n for n in q.notes))

    def test_cte_accepted(self):
        sql = "WITH x AS (SELECT 1 AS n) SELECT * FROM x"
        q = validate_select_query(sql)
        self.assertIn("WITH", q.rewritten.upper())

    def test_sqlite_dialect_uses_limit(self):
        q = validate_select_query("SELECT name FROM users", dialect="sqlite")
        self.assertIn("LIMIT 50000", q.rewritten)

    def test_union_of_selects_is_accepted(self):
        sql = "SELECT 1 UNION SELECT 2"
        q = validate_select_query(sql)
        self.assertIn("UNION", q.rewritten.upper())


class RejectedQueriesTests(unittest.TestCase):
    def assert_rejected(self, sql: str, expect_in_message: str | None = None):
        with self.assertRaises(SqlSafetyError) as cm:
            validate_select_query(sql)
        if expect_in_message:
            self.assertIn(expect_in_message.lower(), str(cm.exception).lower())

    def test_empty(self):
        self.assert_rejected("", "empty")
        self.assert_rejected("   ", "empty")
        self.assert_rejected(None, "empty")  # type: ignore[arg-type]

    def test_drop_table(self):
        self.assert_rejected("DROP TABLE x", "select")

    def test_insert(self):
        self.assert_rejected("INSERT INTO x VALUES (1)", "select")

    def test_update(self):
        self.assert_rejected("UPDATE x SET y = 1", "select")

    def test_delete(self):
        self.assert_rejected("DELETE FROM x", "select")

    def test_truncate(self):
        self.assert_rejected("TRUNCATE TABLE x")

    def test_alter(self):
        self.assert_rejected("ALTER TABLE x ADD col INT")

    def test_two_statements_rejected(self):
        self.assert_rejected("SELECT 1; SELECT 2", "one statement")

    def test_system_schema_rejected(self):
        self.assert_rejected("SELECT * FROM sys.tables", "system schema")
        self.assert_rejected("SELECT * FROM information_schema.columns", "system schema")

    def test_xp_cmdshell_rejected(self):
        self.assert_rejected('EXEC xp_cmdshell "dir"', "disallowed")

    def test_openrowset_rejected(self):
        self.assert_rejected("SELECT * FROM OPENROWSET('a', 'b', 'c')", "disallowed")

    def test_parameter_marker_rejected(self):
        self.assert_rejected("SELECT * FROM users WHERE id = ?", "parameter")


if __name__ == "__main__":
    unittest.main()
