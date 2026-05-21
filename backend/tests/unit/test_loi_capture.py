"""Tests for the Convert-as-LOI flow.

The Convert action (Stage-1 forward gate) used to always capture a
formal PO. The user-driven follow-up to Phase 1 lets it capture either
a PO or an LOI instead — flagged via ``isLOI`` on the body. When LOI:
  * ``poNo`` may be omitted; service auto-generates ``LOI-{quotId}-{seq}``.
  * ``poDate`` doubles as the LOI date.
  * ``loiText`` is an optional free-text body.

These tests pin the service-layer behaviour. End-to-end coverage of
the route handler lives in ``test_cycle_endpoints`` via the cycle-
scoped append flow which shares the same ``create_or_update_po``
codepath.
"""
from datetime import date, datetime

import pytest

pytestmark = pytest.mark.unit


# Reuse the sqlite-in-memory fixture pattern from sibling tests.

@pytest.fixture
def in_memory_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
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
    from app.models.customer import CustomerMaster
    from app.models.quotation import QuotSummary

    db = in_memory_session
    db.add(CustomerMaster(
        customerId=1, companyId=1, customerName="ACME Construction",
    ))
    quot = QuotSummary(
        quotId=1, companyId=1, customerId=1, quotNo="QUOT-1",
        quotDate=date.today(), status="Approved", versionNo=1,
        createdby=1, createdon=datetime.utcnow(),
    )
    db.add(quot)
    db.flush()
    return quot


def _loi_body(po_no=None, loi_text=None):
    """Compact LOI body factory. poNo defaults to None so the service
    auto-generates it; tests can override for the negative-validation
    paths."""
    from app.schemas.quot_purchase_order import QuotPurchaseOrderBody
    return QuotPurchaseOrderBody(
        isLOI=True,
        poNo=po_no,
        poDate=date.today(),
        customerId=1,
        billingAddressManual="123 Test Lane",
        consigneeAddressManual="Site 7, Industrial Area",
        loiText=loi_text,
    )


def _po_body(po_no="PO-123"):
    from app.schemas.quot_purchase_order import QuotPurchaseOrderBody
    return QuotPurchaseOrderBody(
        isLOI=False,
        poNo=po_no,
        poDate=date.today(),
        customerId=1,
        billingAddressManual="123 Test Lane",
        consigneeAddressManual="Site 7, Industrial Area",
    )


class TestLoiBodyValidation:
    def test_formal_po_requires_po_no(self):
        """Pydantic-level validator: ``isLOI=False`` + no poNo must
        reject at schema construction, before the service even sees
        it."""
        from pydantic import ValidationError
        from app.schemas.quot_purchase_order import QuotPurchaseOrderBody
        with pytest.raises(ValidationError) as exc:
            QuotPurchaseOrderBody(
                isLOI=False, poNo=None, poDate=date.today(),
                customerId=1,
                billingAddressManual="A", consigneeAddressManual="B",
            )
        assert "poNo is required" in str(exc.value)

    def test_loi_allows_omitted_po_no(self):
        """LOIs may omit poNo entirely — schema accepts it."""
        body = _loi_body(po_no=None)
        assert body.isLOI is True
        assert body.poNo is None

    def test_loi_text_optional(self):
        body = _loi_body(loi_text=None)
        assert body.loiText is None


class TestCreateOrUpdatePoAsLoi:
    def test_create_loi_auto_generates_po_no(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        from app.services.purchase_order_service import create_or_update_po
        po = create_or_update_po(
            in_memory_session, seeded_quotation_and_customer,
            _loi_body(), user_id=1,
        )
        assert po.isLOI is True
        # First LOI on this quotation → seq = 1.
        assert po.poNo == "LOI-1-1"

    def test_loi_text_persists(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        from app.services.purchase_order_service import create_or_update_po
        po = create_or_update_po(
            in_memory_session, seeded_quotation_and_customer,
            _loi_body(loi_text="Customer intends to place a 500MT order "
                               "within 4 weeks subject to final spec sign-off."),
            user_id=1,
        )
        assert po.loiText is not None
        assert "500MT" in po.loiText

    def test_loi_text_whitespace_normalised_to_none(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        """Empty / whitespace-only loiText collapses to None so the
        DB doesn't carry meaningless padding."""
        from app.services.purchase_order_service import create_or_update_po
        po = create_or_update_po(
            in_memory_session, seeded_quotation_and_customer,
            _loi_body(loi_text="   "),
            user_id=1,
        )
        assert po.loiText is None

    def test_formal_po_path_unaffected(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        """Sanity: the existing PO capture path still works — no
        isLOI side-effect on plain-PO calls."""
        from app.services.purchase_order_service import create_or_update_po
        po = create_or_update_po(
            in_memory_session, seeded_quotation_and_customer,
            _po_body("PO-ACME-001"),
            user_id=1,
        )
        assert po.isLOI is False
        assert po.poNo == "PO-ACME-001"
        assert po.loiText is None

    def test_loi_no_increments_per_quotation(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        """Two LOIs on the same quotation get distinct auto-numbers.
        First-class for the post-Phase-1 future where multiple cycles
        each spawn an LOI on the same quotation."""
        from app.services.purchase_order_service import (
            PurchaseOrderConflictError, create_or_update_po,
        )
        # The single-PO ``create_or_update_po`` is idempotent on
        # the same quotation, so to get TWO LOIs we need to bypass
        # the get_po() branch — append the second one directly via
        # the cycle helper which doesn't dedup.
        first = create_or_update_po(
            in_memory_session, seeded_quotation_and_customer,
            _loi_body(), user_id=1,
        )
        assert first.poNo == "LOI-1-1"
        # _resolve_po_no counts existing LOIs on the quotation —
        # the second call should see one and produce LOI-1-2 if we
        # were to make a new row. Verify via the resolver directly.
        from app.services.purchase_order_service import _resolve_po_no
        second_no = _resolve_po_no(
            in_memory_session, seeded_quotation_and_customer, _loi_body(),
        )
        assert second_no == "LOI-1-2"


class TestConvertViaCycleHelpers:
    """Regression for the bug where ``/convert`` created a
    QuotPurchaseOrder row without ``quotOrderCycleId`` — Phase 1A
    made that column NOT NULL on the table, so the legacy insert
    crashed on first use. The fix routes Convert through
    ``start_new_cycle`` + ``append_purchase_order_to_cycle`` so
    Cycle #1 is opened in the same transaction and the FK is
    populated on both the PO and the cloned FWS rows."""

    def test_convert_as_loi_attaches_to_new_cycle_one(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        from app.services.cycle_service import start_new_cycle
        from app.services.purchase_order_service import (
            append_purchase_order_to_cycle,
        )

        # Mimic the route handler's new sequence.
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        po = append_purchase_order_to_cycle(
            in_memory_session, cycle, _loi_body(loi_text="Test intent"),
            user_id=1, is_loi=True,
        )
        # The bug surface: cycle FK must be non-null on the PO row.
        assert po.quotOrderCycleId == cycle.quotOrderCycleId
        assert po.isLOI is True
        assert po.poNo == "LOI-1-1"
        assert po.loiText == "Test intent"
        # Cycle 1 opened and quotation auto-Converted.
        assert cycle.cycleNo == 1
        assert seeded_quotation_and_customer.status == "Converted"

    def test_convert_as_formal_po_attaches_to_new_cycle_one(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        from app.services.cycle_service import start_new_cycle
        from app.services.purchase_order_service import (
            append_purchase_order_to_cycle,
        )

        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        po = append_purchase_order_to_cycle(
            in_memory_session, cycle, _po_body("ACME-PO-001"),
            user_id=1, is_loi=False,
        )
        assert po.quotOrderCycleId == cycle.quotOrderCycleId
        assert po.isLOI is False
        assert po.poNo == "ACME-PO-001"
        assert po.loiText is None

    def test_regenerate_after_approval_forks_new_version(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        """User flow #3: clicking Generate Viability on an Approved
        head must archive the head and create a fresh Draft v+1
        carrying its edited lines forward. The old version stays
        time-travel reachable (isActive=False, still queryable)."""
        from decimal import Decimal
        from app.models.quotation import QuotDetails
        from app.models.quot_viability import (
            QuotViabilityLine, QuotViabilitySheet,
        )
        from app.services.cycle_service import start_new_cycle
        from app.services.purchase_order_service import (
            append_purchase_order_to_cycle,
        )
        from app.services.viability_service import generate_viability_sheet

        # Seed one quoted line + open cycle 1 + capture PO.
        in_memory_session.add(QuotDetails(
            companyId=1,
            quotId=seeded_quotation_and_customer.quotId,
            itemName="TMT 12mm", itemGradeName="Fe550D",
            itemDia="12mm", quantity=Decimal("50.00"),
            TPWGST=Decimal("52000.00"),
            createdby=1,
        ))
        in_memory_session.flush()
        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        append_purchase_order_to_cycle(
            in_memory_session, cycle, _po_body("PO-1"),
            user_id=1, is_loi=False,
        )
        # First generate — creates v1 Draft.
        v1 = generate_viability_sheet(
            in_memory_session,
            quotation=seeded_quotation_and_customer, user_id=1,
        )
        assert v1.versionNo == 1
        assert v1.status == "Draft"
        # Simulate the user approving v1 and tweaking a line.
        v1.status = "Approved"
        # Edit a line so we can confirm the fork carries the edit.
        v1_lines = (
            in_memory_session.query(QuotViabilityLine)
            .filter(QuotViabilityLine.viabilityId == v1.viabilityId)
            .all()
        )
        assert len(v1_lines) >= 1
        v1_lines[0].Marketing = Decimal("1234.00")
        in_memory_session.flush()

        # Second generate — should fork to v2 Draft carrying the edit.
        v2 = generate_viability_sheet(
            in_memory_session,
            quotation=seeded_quotation_and_customer, user_id=1,
        )
        assert v2.viabilityId != v1.viabilityId
        assert v2.versionNo == 2
        assert v2.status == "Draft"
        assert v2.isActive is True
        # v1 archived.
        in_memory_session.refresh(v1)
        assert v1.isActive is False
        # Forked lines carry the previous version's edit forward.
        v2_lines = (
            in_memory_session.query(QuotViabilityLine)
            .filter(QuotViabilityLine.viabilityId == v2.viabilityId)
            .all()
        )
        assert len(v2_lines) == len(v1_lines)
        assert v2_lines[0].Marketing == Decimal("1234.00")

    def test_viability_generation_inherits_cycle_fk(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        """Regression: Phase 1A made ``QuotViabilitySheet.quotOrderCycleId``
        NOT NULL. ``generate_viability_sheet`` must derive the cycle
        from the captured PO (or the quotation's active cycle when no
        PO is present) so the insert satisfies the constraint."""
        from decimal import Decimal
        from app.models.quotation import QuotDetails
        from app.services.cycle_service import start_new_cycle
        from app.services.purchase_order_service import (
            append_purchase_order_to_cycle,
        )
        from app.services.viability_service import generate_viability_sheet

        # Seed a quoted line so the viability has something to clone.
        in_memory_session.add(QuotDetails(
            companyId=1,
            quotId=seeded_quotation_and_customer.quotId,
            itemName="TMT 12mm", itemGradeName="Fe550D",
            itemDia="12mm", quantity=Decimal("50.00"),
            TPWGST=Decimal("52000.00"),
            createdby=1,
        ))
        in_memory_session.flush()

        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        append_purchase_order_to_cycle(
            in_memory_session, cycle, _po_body("PO-1"),
            user_id=1, is_loi=False,
        )
        # seeded_quotation_and_customer.status is now Converted via
        # start_new_cycle's side-effect; viability generation is gated
        # by that status.
        sheet = generate_viability_sheet(
            in_memory_session,
            quotation=seeded_quotation_and_customer,
            user_id=1,
        )
        # The fix: cycle FK populated from the PO.
        assert sheet.quotOrderCycleId == cycle.quotOrderCycleId
        assert sheet.status == "Draft"

    def test_cloned_fws_rows_inherit_cycle_fk(
        self, in_memory_session, seeded_quotation_and_customer,
    ):
        """After Phase 1A the FWS table's ``quotOrderCycleId`` is also
        NOT NULL. ``clone_from_quotation`` reads the column off the
        owning PO so the new WS rows satisfy the constraint without
        an extra arg."""
        from decimal import Decimal
        from app.models.quotation import QuotDetails
        from app.services.cycle_service import start_new_cycle
        from app.services.purchase_order_service import (
            append_purchase_order_to_cycle,
        )
        from app.services.po_working_sheet_service import clone_from_quotation

        # Seed one quoted line so there's something to clone.
        in_memory_session.add(QuotDetails(
            companyId=1,
            quotId=seeded_quotation_and_customer.quotId,
            itemName="TMT 12mm", itemGradeName="Fe550D",
            itemDia="12mm", quantity=Decimal("50.00"),
            TPWGST=Decimal("52000.00"),
            createdby=1,
        ))
        in_memory_session.flush()

        cycle = start_new_cycle(
            in_memory_session, seeded_quotation_and_customer, started_by=1,
        )
        po = append_purchase_order_to_cycle(
            in_memory_session, cycle, _po_body("PO-1"),
            user_id=1, is_loi=False,
        )
        rows = clone_from_quotation(
            in_memory_session, po,
            seeded_quotation_and_customer,
            user_id=1,
        )
        assert len(rows) == 1
        # The fix: every cloned WS row carries the PO's cycle FK.
        assert rows[0].quotOrderCycleId == cycle.quotOrderCycleId
