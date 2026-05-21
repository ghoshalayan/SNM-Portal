"""Tests for the Phase 1B cycle-aware helpers on the PO + FWS services.

Covers the new ``append_purchase_order_to_cycle``,
``list_purchase_orders_in_cycle``, ``clone_working_sheet_for_new_cycle``
functions added alongside the existing single-PO surface during the
back-compat window.

Uses the same sqlite-in-memory fixture shape as ``test_cycle_service``
— FKs off, only the rows the helper touches need to exist.
"""
from datetime import date, datetime
import pytest

from app.services.cycle_service import start_new_cycle
from app.services.purchase_order_service import (
    PurchaseOrderConflictError,
    append_purchase_order_to_cycle,
    list_purchase_orders_in_cycle,
)
from app.services.po_working_sheet_service import (
    clone_working_sheet_for_new_cycle,
    list_working_sheet_for_cycle,
)


pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------
# Fixtures — sqlite in-memory + a seeded Approved quotation
# ----------------------------------------------------------------------

@pytest.fixture
def in_memory_session():
    """Fresh sqlite-in-memory DB with the ORM schema applied. Mirrors
    the fixture from ``test_cycle_service`` — duplicated here so this
    file is self-contained (fixtures don't auto-import across files
    when modules are in different test packages)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    # Force registration of every model on Base.metadata.
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
def seeded_quotation_and_customer(in_memory_session):
    """A QuotSummary in ``Approved`` status + the CustomerMaster row
    its PO body will reference. Sqlite FKs are off so we skip the
    Contact/Site rows — they're optional on the PO body."""
    from app.models.customer import CustomerMaster
    from app.models.quotation import QuotSummary

    db = in_memory_session
    customer = CustomerMaster(
        customerId=1, companyId=1, customerName="ACME Construction",
    )
    db.add(customer)
    quot = QuotSummary(
        quotId=1, companyId=1, customerId=1, quotNo="QUOT-1",
        quotDate=date.today(), status="Approved", versionNo=1,
        createdby=1, createdon=datetime.utcnow(),
    )
    db.add(quot)
    db.flush()
    return quot


def _make_po_body(po_no: str = "PO-001"):
    """Compact factory for the schema body the append helper expects.
    Billing + consignee addresses pass manual values so the
    "exactly one of {site, manual}" validation is satisfied without
    needing to seed CustomerSite rows in the fixture."""
    from app.schemas.quot_purchase_order import QuotPurchaseOrderBody
    return QuotPurchaseOrderBody(
        poNo=po_no, poDate=date.today(), customerId=1,
        billingAddressManual="123 Test Bldg, Test City",
        consigneeAddressManual="Site 7, Test Industrial Area",
    )


# ----------------------------------------------------------------------
# append_purchase_order_to_cycle
# ----------------------------------------------------------------------

class TestAppendPurchaseOrderToCycle:
    def test_append_first_po_assigns_sequence_one(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        po = append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body(), user_id=1,
        )
        assert po.loiSequence == 1
        assert po.isLOI is False
        assert po.status == "Draft"
        assert po.quotOrderCycleId == cycle.quotOrderCycleId

    def test_loi_flag_propagates(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        loi = append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("LOI-001"),
            user_id=1, is_loi=True,
        )
        assert loi.isLOI is True

    def test_sequence_increments_per_cycle(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        first = append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("PO-1"), user_id=1,
        )
        second = append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("PO-2"), user_id=1,
            is_loi=True,
        )
        third = append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("PO-3"), user_id=1,
        )
        assert [first.loiSequence, second.loiSequence, third.loiSequence] == [1, 2, 3]

    def test_cannot_append_to_closed_cycle(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        cycle.status = "Complete"
        with pytest.raises(PurchaseOrderConflictError) as exc:
            append_purchase_order_to_cycle(
                in_memory_session, cycle, _make_po_body(), user_id=1,
            )
        assert "Active" in str(exc.value)


class TestListPurchaseOrdersInCycle:
    def test_empty_cycle_returns_empty_list(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        assert list_purchase_orders_in_cycle(in_memory_session, cycle) == []

    def test_returns_rows_in_sequence_order(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("PO-1"), user_id=1,
        )
        # LOI captures auto-generate their poNo regardless of what the
        # caller supplies — the user-supplied value is ignored, the
        # server stamps ``LOI-{quotId}-{seq}`` for traceability.
        append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("PO-2"),
            user_id=1, is_loi=True,
        )
        rows = list_purchase_orders_in_cycle(in_memory_session, cycle)
        assert [r.poNo for r in rows] == ["PO-1", "LOI-1-1"]
        assert [r.loiSequence for r in rows] == [1, 2]
        assert [r.isLOI for r in rows] == [False, True]


# ----------------------------------------------------------------------
# clone_working_sheet_for_new_cycle
# ----------------------------------------------------------------------

class TestCloneWorkingSheetForNewCycle:
    def test_inherits_lines_from_parent_working_sheet(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        from decimal import Decimal
        from app.models.quot_po_working_sheet import QuotPOWorkingSheet

        # Cycle 1: spawn it + simulate Approved → seed one WS row.
        first_cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        first_po = append_purchase_order_to_cycle(
            in_memory_session, first_cycle, _make_po_body("PO-1"),
            user_id=1,
        )
        ws_row = QuotPOWorkingSheet(
            companyId=1,
            quotPOId=first_po.quotPOId,
            quotOrderCycleId=first_cycle.quotOrderCycleId,
            itemName="TMT Bar", itemGradeName="Fe550D",
            itemDia="12mm", itemLength="12 MTRS", itemUnit="MT",
            quantity=Decimal("100.00"),
            TPWGST=Decimal("52000.00"), Marketing=Decimal("500.00"),
            createdby=1,
        )
        in_memory_session.add(ws_row)
        in_memory_session.flush()

        # Cycle 2: start + append a PO + clone WS from cycle 1.
        second_cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        second_po = append_purchase_order_to_cycle(
            in_memory_session, second_cycle, _make_po_body("PO-2"),
            user_id=1,
        )
        cloned = clone_working_sheet_for_new_cycle(
            in_memory_session,
            new_cycle=second_cycle,
            parent_cycle=first_cycle,
            owning_po=second_po,
            user_id=1,
        )

        assert len(cloned) == 1
        new_row = cloned[0]
        assert new_row.quotOrderCycleId == second_cycle.quotOrderCycleId
        assert new_row.quotPOId == second_po.quotPOId
        # Cost heads come across verbatim (Decimal precision preserved).
        assert new_row.TPWGST == Decimal("52000.00")
        assert new_row.Marketing == Decimal("500.00")
        assert new_row.itemGradeName == "Fe550D"

    def test_returns_empty_when_parent_has_no_source(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        # Parent cycle has neither viability nor WS rows → 'none' source.
        first_cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        second_cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        owning_po = append_purchase_order_to_cycle(
            in_memory_session, second_cycle, _make_po_body("PO-2"),
            user_id=1,
        )
        cloned = clone_working_sheet_for_new_cycle(
            in_memory_session,
            new_cycle=second_cycle,
            parent_cycle=first_cycle,
            owning_po=owning_po,
            user_id=1,
        )
        assert cloned == []

    def test_rejects_owning_po_from_wrong_cycle(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        cycle_a = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        cycle_b = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        po_in_a = append_purchase_order_to_cycle(
            in_memory_session, cycle_a, _make_po_body("PO-A"), user_id=1,
        )
        # Try to clone into B but pass A's PO — should reject.
        with pytest.raises(ValueError) as exc:
            clone_working_sheet_for_new_cycle(
                in_memory_session,
                new_cycle=cycle_b,
                parent_cycle=cycle_a,
                owning_po=po_in_a,
                user_id=1,
            )
        assert "owning_po must belong to new_cycle" in str(exc.value)


class TestListWorkingSheetForCycle:
    def test_returns_only_active_rows_for_cycle(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        from decimal import Decimal
        from app.models.quot_po_working_sheet import QuotPOWorkingSheet

        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        po = append_purchase_order_to_cycle(
            in_memory_session, cycle, _make_po_body("PO-1"), user_id=1,
        )
        active = QuotPOWorkingSheet(
            companyId=1, quotPOId=po.quotPOId,
            quotOrderCycleId=cycle.quotOrderCycleId,
            itemName="A", TPWGST=Decimal("100"), createdby=1,
        )
        inactive = QuotPOWorkingSheet(
            companyId=1, quotPOId=po.quotPOId,
            quotOrderCycleId=cycle.quotOrderCycleId,
            itemName="B-deleted", TPWGST=Decimal("200"),
            createdby=1, isActive=False,
        )
        in_memory_session.add_all([active, inactive])
        in_memory_session.flush()

        rows = list_working_sheet_for_cycle(in_memory_session, cycle)
        assert len(rows) == 1
        assert rows[0].itemName == "A"
