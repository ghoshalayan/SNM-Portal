"""Introspector tests.

Run against in-memory SQLite — no SNM models touched, which proves
kpi_studio works as a standalone package.

Run with: python -m unittest tests.kpi_studio.test_introspector
"""
from __future__ import annotations

import unittest

from sqlalchemy import (
    Column, ForeignKey, Integer, MetaData, String, Table, create_engine,
)
from sqlalchemy.orm import sessionmaker

from kpi_studio.config import KpiStudioConfig
from kpi_studio.models import KpiBase
from kpi_studio.services import introspector


def _make_target_engine():
    """Build a SQLite engine with two related tables for the introspector
    to find. Uses raw Table() to avoid pulling in any host models."""
    engine = create_engine("sqlite:///:memory:")
    md = MetaData()
    Table(
        "customer", md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
    )
    Table(
        "orders", md,
        Column("id", Integer, primary_key=True),
        Column("customer_id", Integer, ForeignKey("customer.id"), nullable=False),
        Column("total", Integer),
    )
    md.create_all(engine)
    return engine


def _make_metadata_db():
    """Engine + session factory hosting the kpi_* tables."""
    engine = create_engine("sqlite:///:memory:")
    KpiBase.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _config(target_engine):
    return KpiStudioConfig(
        auth_dep=lambda: None,
        metadata_session_factory=_make_metadata_db(),
        target_engine=target_engine,
    )


class ReflectSchemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = _make_target_engine()
        self.cfg = _config(self.engine)

    def test_finds_user_tables(self):
        payload = introspector.reflect_schema(self.engine, self.cfg)
        names = sorted(t.name for t in payload.tables)
        self.assertEqual(names, ["customer", "orders"])

    def test_skips_excluded_prefix(self):
        # Default config hides anything starting with "kpi_". Add a kpi_xx
        # table to the target schema and ensure it doesn't appear.
        from sqlalchemy import MetaData, Table, Column, Integer
        md = MetaData()
        Table("kpi_internal", md, Column("id", Integer, primary_key=True))
        md.create_all(self.engine)

        payload = introspector.reflect_schema(self.engine, self.cfg)
        names = {t.name for t in payload.tables}
        self.assertNotIn("kpi_internal", names)

    def test_captures_foreign_keys(self):
        payload = introspector.reflect_schema(self.engine, self.cfg)
        orders = next(t for t in payload.tables if t.name == "orders")
        self.assertEqual(len(orders.foreign_keys), 1)
        fk = orders.foreign_keys[0]
        self.assertEqual(fk.constrained_columns, ["customer_id"])
        self.assertEqual(fk.referred_table, "customer")
        self.assertEqual(fk.referred_columns, ["id"])

    def test_columns_include_pk_and_nullability(self):
        payload = introspector.reflect_schema(self.engine, self.cfg)
        customer = next(t for t in payload.tables if t.name == "customer")
        cols = {c.name: c for c in customer.columns}
        self.assertTrue(cols["id"].primary_key)
        self.assertFalse(cols["name"].nullable)

    def test_dialect_is_recorded(self):
        payload = introspector.reflect_schema(self.engine, self.cfg)
        self.assertEqual(payload.dialect, "sqlite")


class GraphProjectionTests(unittest.TestCase):
    def test_graph_has_one_node_per_table_and_one_edge_per_fk(self):
        engine = _make_target_engine()
        cfg = _config(engine)
        payload = introspector.reflect_schema(engine, cfg)
        graph = introspector.build_graph(payload)

        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.edges), 1)
        edge = graph.edges[0]
        # Source = FK holder, target = referenced table.
        self.assertTrue(edge.source.endswith("orders"))
        self.assertTrue(edge.target.endswith("customer"))

    def test_dangling_fk_is_dropped(self):
        # Create FK to a table that's then excluded from the snapshot via
        # config. The edge should be dropped, not emitted with a missing target.
        engine = _make_target_engine()
        cfg = KpiStudioConfig(
            auth_dep=lambda: None,
            metadata_session_factory=_make_metadata_db(),
            target_engine=engine,
            excluded_table_patterns=("kpi_", "alembic_", "sysdiagrams", "customer"),
        )
        payload = introspector.reflect_schema(engine, cfg)
        graph = introspector.build_graph(payload)
        # customer is hidden, so the orders→customer edge must be dropped.
        self.assertEqual(graph.edges, [])


class PersistenceTests(unittest.TestCase):
    def test_persist_demotes_prior_current(self):
        engine = _make_target_engine()
        Session = _make_metadata_db()
        cfg = KpiStudioConfig(
            auth_dep=lambda: None,
            metadata_session_factory=Session,
            target_engine=engine,
        )
        db = Session()
        try:
            payload = introspector.reflect_schema(engine, cfg)
            first = introspector.persist_snapshot(db, payload, created_by=1)
            second = introspector.persist_snapshot(db, payload, created_by=2)

            self.assertNotEqual(first.snapshot_id, second.snapshot_id)
            db.refresh(first)
            self.assertFalse(first.is_current)
            self.assertTrue(second.is_current)

            current = introspector.get_current_snapshot(db)
            self.assertEqual(current.snapshot_id, second.snapshot_id)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
