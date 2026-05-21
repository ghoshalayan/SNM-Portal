"""Unit tests for cycle_service.

Two layers:

  1. **Pure-function tests** for ``can_close_cycle()`` and
     ``can_abandon_cycle()`` — no DB, just truth-table coverage of the
     state-machine guards.
  2. **In-memory integration tests** for ``start_new_cycle``,
     ``close_cycle``, ``abandon_cycle`` using a sqlite-backed Session.
     Verifies side effects (status transitions, notes timestamping,
     cycle numbering, quotation auto-Convert) end-to-end.

The sqlite path doesn't exercise the production SQL Server-specific
filtered indexes; those are validated only by the migration's
``mssql_where``. Sqlite + ``sqlite_where`` give us coverage of the
SQLAlchemy mapping itself.
"""
import pytest

from app.services.cycle_service import (
    CycleValidationError,
    can_abandon_cycle,
    can_close_cycle,
)


pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------
# Pure-function: can_close_cycle
# ----------------------------------------------------------------------

class TestCanCloseCycle:
    """Truth-table on the close-cycle eligibility check. All three
    inputs must be satisfied; failures should accumulate so the UI
    can show every blocker at once."""

    def test_all_conditions_met_returns_ok(self):
        result = can_close_cycle(
            cycle_status="Active",
            has_approved_annexure=True,
            has_formal_po=True,
        )
        assert result.ok is True
        assert result.blockers == []

    def test_wrong_status_blocks(self):
        result = can_close_cycle(
            cycle_status="Complete",
            has_approved_annexure=True,
            has_formal_po=True,
        )
        assert result.ok is False
        assert any("Active" in b for b in result.blockers)

    def test_missing_annexure_blocks(self):
        result = can_close_cycle(
            cycle_status="Active",
            has_approved_annexure=False,
            has_formal_po=True,
        )
        assert result.ok is False
        assert any("annexure" in b.lower() for b in result.blockers)

    def test_only_loi_blocks(self):
        result = can_close_cycle(
            cycle_status="Active",
            has_approved_annexure=True,
            has_formal_po=False,
        )
        assert result.ok is False
        assert any("formal PO" in b or "PO" in b for b in result.blockers)

    def test_all_three_fail_lists_all_blockers(self):
        """Failure modes must accumulate — the UI should show one
        dialog with N reasons, not N dialogs with one reason each."""
        result = can_close_cycle(
            cycle_status="Abandoned",
            has_approved_annexure=False,
            has_formal_po=False,
        )
        assert result.ok is False
        assert len(result.blockers) == 3


# ----------------------------------------------------------------------
# Pure-function: can_abandon_cycle
# ----------------------------------------------------------------------

class TestCanAbandonCycle:
    def test_active_cycle_can_be_abandoned(self):
        assert can_abandon_cycle("Active").ok is True

    @pytest.mark.parametrize("status", ["Complete", "Abandoned"])
    def test_non_active_cycle_cannot_be_abandoned(self, status):
        result = can_abandon_cycle(status)
        assert result.ok is False
        assert any("Active" in b for b in result.blockers)


# ----------------------------------------------------------------------
# In-memory integration tests (sqlite via SQLAlchemy)
# ----------------------------------------------------------------------

@pytest.fixture
def in_memory_session():
    """Spin up a fresh sqlite-in-memory DB with the ORM schema applied.

    Every test gets a clean DB — no fixtures bleed across tests. The
    ``Base.metadata.create_all`` call uses the ``sqlite_where``
    annotation on the filtered unique index so the QuotOrderCycle
    table builds cleanly on sqlite (production uses ``mssql_where``).
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    # Triggers the imports of every model so ``Base.metadata`` has the
    # full ORM schema. Without this, ``create_all`` skips tables that
    # weren't imported yet.
    import app.models  # noqa: F401
    from app.models import (  # noqa: F401
        company, customer, customer_classification, contact_type,
        cost_template, communication, cost_point, delivery, dia,
        enquiry, financial_year, item, lifecycle_unlock_audit, location,
        menu, ownership_transfer, quot_activity_log, quot_annexure,
        quot_order_cycle, quot_po_working_sheet, quot_purchase_order,
        quot_viability, quotation, quotation_format, raw_material_cost,
        raw_material_cost_log, role_menu_map, terms_condition, user,
        user_location_map, asset,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def seeded_quotation(in_memory_session):
    """Insert a minimal QuotSummary so ``start_new_cycle`` has a valid
    target. Sqlite has FK enforcement OFF by default, so we can write
    the QuotSummary without seeding Company / User / Customer parent
    rows — keeps the fixture readable and decouples it from those
    models' constantly-evolving NOT NULL surfaces. Production SQL
    Server still enforces every FK; this fixture is only for
    service-layer state-machine coverage.
    """
    from datetime import datetime, date

    from app.models.quotation import QuotSummary

    db = in_memory_session
    quot = QuotSummary(
        quotId=1, companyId=1, customerId=1, quotNo="QUOT-1",
        quotDate=date.today(),
        status="Approved", versionNo=1,
        createdby=1, createdon=datetime.utcnow(),
    )
    db.add(quot)
    db.flush()
    return quot


class TestStartNewCycle:
    def test_first_cycle_on_approved_quotation_converts_it(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import start_new_cycle

        cycle = start_new_cycle(
            in_memory_session, seeded_quotation, started_by=1,
        )

        assert cycle.cycleNo == 1
        assert cycle.status == "Active"
        assert cycle.parentCycleId is None
        # Quotation auto-Convert side effect
        assert seeded_quotation.status == "Converted"
        assert seeded_quotation.convertedOn is not None
        assert seeded_quotation.convertedBy == 1

    def test_second_cycle_auto_links_parent(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import start_new_cycle

        first = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        second = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)

        assert second.cycleNo == 2
        assert second.parentCycleId == first.quotOrderCycleId

    def test_second_cycle_does_not_re_convert_quotation(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import start_new_cycle

        start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        original_converted_on = seeded_quotation.convertedOn
        start_new_cycle(in_memory_session, seeded_quotation, started_by=1)

        # Re-converting would clobber the original timestamp.
        assert seeded_quotation.convertedOn == original_converted_on
        assert seeded_quotation.status == "Converted"

    def test_rejects_quotation_in_wrong_status(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import start_new_cycle

        seeded_quotation.status = "Draft"
        with pytest.raises(CycleValidationError) as exc:
            start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        assert "Approved or Converted" in str(exc.value)


class TestCloseCycle:
    def test_close_fails_without_preconditions(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import close_cycle, start_new_cycle

        cycle = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        with pytest.raises(CycleValidationError) as exc:
            close_cycle(in_memory_session, cycle, user_id=1)
        # Both preconditions should fail (no annexure, no PO).
        assert "annexure" in str(exc.value).lower()
        assert "PO" in str(exc.value)

    def test_close_succeeds_with_annexure_and_po(
        self, in_memory_session, seeded_quotation,
    ):
        from datetime import date
        from app.models.quot_purchase_order import QuotPurchaseOrder
        from app.models.quot_annexure import QuotAnnexure
        from app.services.cycle_service import close_cycle, start_new_cycle

        cycle = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        po = QuotPurchaseOrder(
            companyId=1, quotId=seeded_quotation.quotId,
            quotOrderCycleId=cycle.quotOrderCycleId,
            isLOI=False, status="Submitted",
            poNo="PO-1", poDate=date.today(),
            customerId=1, createdby=1,
        )
        in_memory_session.add(po)
        annexure = QuotAnnexure(
            companyId=1, quotId=seeded_quotation.quotId,
            quotOrderCycleId=cycle.quotOrderCycleId,
            status="Approved", versionNo=1, createdby=1,
        )
        in_memory_session.add(annexure)
        in_memory_session.flush()

        result = close_cycle(
            in_memory_session, cycle, user_id=1, reason="all delivered",
        )
        assert result.status == "Complete"
        assert result.closedBy == 1
        assert result.closedOn is not None
        assert "all delivered" in (result.notes or "")

    def test_loi_only_cannot_close(
        self, in_memory_session, seeded_quotation,
    ):
        from datetime import date
        from app.models.quot_purchase_order import QuotPurchaseOrder
        from app.models.quot_annexure import QuotAnnexure
        from app.services.cycle_service import close_cycle, start_new_cycle

        cycle = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        # Only an LOI — no formal PO
        loi = QuotPurchaseOrder(
            companyId=1, quotId=seeded_quotation.quotId,
            quotOrderCycleId=cycle.quotOrderCycleId,
            isLOI=True, status="Submitted",
            poNo="LOI-1", poDate=date.today(),
            customerId=1, createdby=1,
        )
        in_memory_session.add(loi)
        annexure = QuotAnnexure(
            companyId=1, quotId=seeded_quotation.quotId,
            quotOrderCycleId=cycle.quotOrderCycleId,
            status="Approved", versionNo=1, createdby=1,
        )
        in_memory_session.add(annexure)
        in_memory_session.flush()

        with pytest.raises(CycleValidationError) as exc:
            close_cycle(in_memory_session, cycle, user_id=1)
        assert "formal PO" in str(exc.value)


class TestAbandonCycle:
    def test_active_cycle_can_be_abandoned(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import abandon_cycle, start_new_cycle

        cycle = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        result = abandon_cycle(
            in_memory_session, cycle, user_id=1, reason="customer cancelled",
        )
        assert result.status == "Abandoned"
        assert result.closedBy == 1
        assert "customer cancelled" in (result.notes or "")

    def test_cannot_abandon_already_closed_cycle(
        self, in_memory_session, seeded_quotation,
    ):
        from app.services.cycle_service import abandon_cycle, start_new_cycle

        cycle = start_new_cycle(in_memory_session, seeded_quotation, started_by=1)
        cycle.status = "Complete"
        with pytest.raises(CycleValidationError):
            abandon_cycle(in_memory_session, cycle, user_id=1)
