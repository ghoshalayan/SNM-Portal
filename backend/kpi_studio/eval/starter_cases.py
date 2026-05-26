"""Starter eval cases for the SNM Portal schema.

Ten hand-authored regression cases that exercise the NL→SQL pipeline
against the host application's core tables (CustomerMaster, QuotSummary,
QuotDetails, CustomerEnquiry, etc.). Used by the ``seed-starter``
subcommand of ``python -m kpi_studio.eval``.

Why ten and why these prompts:

* Coverage of the common SQL shapes the agent must handle correctly —
  simple aggregates, JOINs, anti-joins, GROUP BY + ORDER BY + LIMIT,
  HAVING, and "latest version per parent" idioms.
* Each case is small enough that a human can verify the golden SQL
  by reading it, but real enough that the LLM has to ground itself in
  the actual schema rather than guess column names.
* Tags split the set so CI can run ``--tags critical`` for a fast
  smoke (cases 1-4) or ``--tags critical aggregation join`` for the
  full sweep.

Authoring rules followed here:

* ``expected_tables`` lists ONLY the tables that MUST appear in the
  generated SQL. The pipeline is allowed to JOIN extras unless we
  set ``strict_tables=True`` (used sparingly — only for tenant-
  leakage checks, which we don't author yet).
* ``expected_columns`` uses fully-qualified ``Table.column`` names so
  the comparator can match unambiguously even when the LLM picks a
  different alias.
* ``golden_sql`` is the canonical human-written version. The
  comparator never matches verbatim — it's printed as a diff hint in
  the failure report.
* ``expected_row_count_*`` are set only when we can predict the shape
  (e.g. a single-row aggregate). For variable-shape results we leave
  both ``None`` and rely on the other comparators.
"""
from __future__ import annotations

from typing import TypedDict


class StarterCase(TypedDict, total=False):
    name: str
    prompt: str
    expected_tables: list[str]
    expected_columns: list[str]
    expected_row_count_min: int
    expected_row_count_max: int
    golden_sql: str
    strict_tables: bool
    tags: list[str]


STARTER_CASES: list[StarterCase] = [
    {
        "name": "Active customer count",
        "prompt": "How many active customers do we have?",
        "expected_tables": ["CustomerMaster"],
        "expected_row_count_min": 1,
        "expected_row_count_max": 1,
        "golden_sql": (
            "SELECT COUNT(*) AS customer_count "
            "FROM CustomerMaster "
            "WHERE isActive = 1"
        ),
        "tags": ["critical", "aggregation"],
    },
    {
        "name": "Quotation count by status",
        "prompt": "Show me the count of quotations grouped by their status.",
        "expected_tables": ["QuotSummary"],
        "expected_columns": ["QuotSummary.status"],
        "golden_sql": (
            "SELECT status, COUNT(*) AS quotation_count "
            "FROM QuotSummary "
            "WHERE isActive = 1 "
            "GROUP BY status"
        ),
        "tags": ["critical", "aggregation"],
    },
    {
        "name": "Top 10 customers by quotation count",
        "prompt": (
            "Which 10 customers have the most quotations? "
            "Show the customer name and the count."
        ),
        "expected_tables": ["CustomerMaster", "QuotSummary"],
        "expected_columns": ["CustomerMaster.customerName"],
        "expected_row_count_max": 10,
        "golden_sql": (
            "SELECT TOP 10 c.customerName, COUNT(q.quotId) AS quotation_count "
            "FROM CustomerMaster c "
            "JOIN QuotSummary q ON q.customerId = c.customerId "
            "WHERE c.isActive = 1 AND q.isActive = 1 "
            "GROUP BY c.customerName "
            "ORDER BY quotation_count DESC"
        ),
        "tags": ["critical", "join", "aggregation"],
    },
    {
        "name": "Recent enquiries (last 30 days)",
        "prompt": "List enquiries created in the last 30 days.",
        "expected_tables": ["CustomerEnquiry"],
        "golden_sql": (
            "SELECT * FROM CustomerEnquiry "
            "WHERE createdon >= DATEADD(day, -30, GETDATE()) "
            "AND isActive = 1 "
            "ORDER BY createdon DESC"
        ),
        "tags": ["critical", "time-filter"],
    },
    {
        "name": "Approved quotations without a PO",
        "prompt": (
            "Find approved quotations that don't have any purchase order "
            "attached yet."
        ),
        "expected_tables": ["QuotSummary", "QuotPurchaseOrder"],
        "golden_sql": (
            "SELECT q.quotId, q.quotNo, q.customerId "
            "FROM QuotSummary q "
            "LEFT JOIN QuotPurchaseOrder p "
            "  ON p.quotId = q.quotId AND p.isActive = 1 "
            "WHERE q.status = 'Approved' "
            "  AND q.isActive = 1 "
            "  AND p.quotPOId IS NULL"
        ),
        "tags": ["anti-join", "join"],
    },
    {
        "name": "Top items by total quantity quoted",
        "prompt": "What are the top 5 items by total quantity quoted across all quotations?",
        "expected_tables": ["QuotDetails"],
        "expected_row_count_max": 5,
        "golden_sql": (
            "SELECT TOP 5 itemName, SUM(quantity) AS total_quantity "
            "FROM QuotDetails "
            "WHERE isActive = 1 AND itemName IS NOT NULL "
            "GROUP BY itemName "
            "ORDER BY total_quantity DESC"
        ),
        "tags": ["aggregation", "ordering"],
    },
    {
        "name": "User count per role",
        "prompt": "How many active users are mapped to each role?",
        "expected_tables": ["UserRoleMap", "RoleMaster"],
        "expected_columns": ["RoleMaster.roleName"],
        "golden_sql": (
            "SELECT r.roleName, COUNT(u.userRoleMapId) AS user_count "
            "FROM RoleMaster r "
            "LEFT JOIN UserRoleMap u "
            "  ON u.roleId = r.roleId AND u.isActive = 1 "
            "WHERE r.isActive = 1 "
            "GROUP BY r.roleName "
            "ORDER BY user_count DESC"
        ),
        "tags": ["join", "aggregation"],
    },
    {
        "name": "Approved annexures this month",
        "prompt": "How many annexures were approved this month?",
        "expected_tables": ["QuotAnnexure"],
        "expected_row_count_min": 1,
        "expected_row_count_max": 1,
        "golden_sql": (
            "SELECT COUNT(*) AS approved_this_month "
            "FROM QuotAnnexure "
            "WHERE status = 'Approved' "
            "  AND approvedon >= DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1) "
            "  AND isActive = 1"
        ),
        "tags": ["aggregation", "time-filter"],
    },
    {
        "name": "Quotations with multiple call-off cycles",
        "prompt": "Show quotations that have more than one call-off cycle.",
        "expected_tables": ["QuotOrderCycle"],
        "golden_sql": (
            "SELECT quotId, COUNT(*) AS cycle_count "
            "FROM QuotOrderCycle "
            "WHERE isActive = 1 "
            "GROUP BY quotId "
            "HAVING COUNT(*) > 1"
        ),
        "tags": ["aggregation", "having"],
    },
    {
        "name": "Latest viability version per quotation",
        "prompt": (
            "For each quotation, what is the latest viability sheet "
            "version number?"
        ),
        "expected_tables": ["QuotViabilitySheet"],
        "expected_columns": ["QuotViabilitySheet.quotId"],
        "golden_sql": (
            "SELECT quotId, MAX(versionNo) AS latest_version "
            "FROM QuotViabilitySheet "
            "WHERE isActive = 1 "
            "GROUP BY quotId"
        ),
        "tags": ["aggregation", "latest-per-group"],
    },
]
