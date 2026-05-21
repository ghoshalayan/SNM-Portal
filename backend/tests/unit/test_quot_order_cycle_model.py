"""Unit smoke tests for the Phase 1A LOI/Cycle data model.

These tests verify the SQLAlchemy mapping declarations (table names,
column names, foreign keys, relationships, indexes) WITHOUT touching a
real database. Catches regressions like a dropped column or a renamed
FK target the moment the model file is edited.

DB-integration tests (cycle CRUD, backfill correctness, multi-cycle
queries) land in Phase 1B once the service layer arrives.
"""
import pytest

from app.models.quot_order_cycle import QuotOrderCycle
from app.models.quot_purchase_order import QuotPurchaseOrder
from app.models.quot_po_working_sheet import QuotPOWorkingSheet
from app.models.quot_viability import QuotViabilitySheet
from app.models.quot_annexure import QuotAnnexure
from app.models.lifecycle_unlock_audit import LifecycleUnlockAudit
from app.models.role_menu_map import RoleMenuMap


pytestmark = pytest.mark.unit


class TestQuotOrderCycleModel:
    """The new table — every column the migration creates must be on
    the SQLAlchemy class too."""

    def test_table_name(self):
        assert QuotOrderCycle.__tablename__ == "QuotOrderCycle"

    def test_primary_key(self):
        cols = QuotOrderCycle.__table__.primary_key.columns
        assert [c.name for c in cols] == ["quotOrderCycleId"]

    def test_required_columns_present(self):
        expected = {
            "quotOrderCycleId", "companyId", "quotId", "cycleNo",
            "status", "parentCycleId", "startedOn", "startedBy",
            "closedOn", "closedBy", "notes",
            # AuditMixin columns
            "createdon", "createdby", "lastupdateon", "lastupdateby", "isActive",
        }
        actual = {c.name for c in QuotOrderCycle.__table__.columns}
        missing = expected - actual
        assert not missing, f"Missing columns on QuotOrderCycle: {missing}"

    def test_parent_cycle_self_referential_fk(self):
        col = QuotOrderCycle.__table__.c.parentCycleId
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].column.table.name == "QuotOrderCycle"
        assert fks[0].column.name == "quotOrderCycleId"

    def test_quot_id_fk_to_quot_summary(self):
        col = QuotOrderCycle.__table__.c.quotId
        fks = list(col.foreign_keys)
        assert any(fk.column.table.name == "QuotSummary" for fk in fks)

    def test_started_by_and_closed_by_fk_to_user(self):
        for name in ("startedBy", "closedBy"):
            col = QuotOrderCycle.__table__.c[name]
            fks = list(col.foreign_keys)
            assert any(fk.column.table.name == "UserMaster" for fk in fks), name

    # Indexes for QuotOrderCycle (incl. the filtered UNIQUE) live in
    # the Phase 1A migration, not on the model — matches the rest of
    # the codebase. The migration's index names are pinned by file
    # review; no model-level assertion needed here.


class TestQuotPurchaseOrderCycleColumns:
    def test_new_columns_present(self):
        cols = {c.name for c in QuotPurchaseOrder.__table__.columns}
        assert {"quotOrderCycleId", "isLOI", "loiSequence"} <= cols

    def test_is_loi_defaults_to_false(self):
        # Server default should keep all legacy rows as PO (not LOI).
        is_loi_col = QuotPurchaseOrder.__table__.c.isLOI
        default = is_loi_col.default
        assert default is not None
        assert default.arg is False

    def test_cycle_id_fk_target(self):
        col = QuotPurchaseOrder.__table__.c.quotOrderCycleId
        fks = list(col.foreign_keys)
        assert any(fk.column.table.name == "QuotOrderCycle" for fk in fks)


class TestDownstreamTablesCycleColumn:
    """Each of the four child tables gained ``quotOrderCycleId``."""

    @pytest.mark.parametrize("model", [
        QuotPOWorkingSheet,
        QuotViabilitySheet,
        QuotAnnexure,
        LifecycleUnlockAudit,
    ])
    def test_has_cycle_id_column(self, model):
        cols = {c.name for c in model.__table__.columns}
        assert "quotOrderCycleId" in cols, f"{model.__name__} missing quotOrderCycleId"

    @pytest.mark.parametrize("model", [
        QuotPOWorkingSheet,
        QuotViabilitySheet,
        QuotAnnexure,
        LifecycleUnlockAudit,
    ])
    def test_cycle_id_fk_to_quot_order_cycle(self, model):
        col = model.__table__.c.quotOrderCycleId
        fks = list(col.foreign_keys)
        assert any(fk.column.table.name == "QuotOrderCycle" for fk in fks)


class TestRoleMenuMapNewFlags:
    def test_can_capture_loi_present(self):
        cols = {c.name for c in RoleMenuMap.__table__.columns}
        assert "CanCaptureLOI" in cols

    def test_can_start_new_cycle_present(self):
        cols = {c.name for c in RoleMenuMap.__table__.columns}
        assert "CanStartNewCycle" in cols

    def test_both_flags_default_to_false(self):
        """New flags MUST default to OFF — existing custom roles get
        the new flags as False until an admin grants them."""
        for name in ("CanCaptureLOI", "CanStartNewCycle"):
            col = RoleMenuMap.__table__.c[name]
            assert col.default is not None, f"{name} has no Python default"
            assert col.default.arg is False, f"{name} default not False"
            assert not col.nullable, f"{name} should be NOT NULL"
