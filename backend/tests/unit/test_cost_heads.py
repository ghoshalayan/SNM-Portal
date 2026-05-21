"""Unit tests for the cost-head sum helper (CR #2 — auto-deduct CD/SplDisc).

Covers the contract:
  * Regular cost heads accumulate positively.
  * CD + SplDisc are deducted regardless of input shape.
  * Decimal in → Decimal out; float in → float out; mixed input picks
    Decimal precision (first non-None value wins).
  * Missing keys / None values are skipped (no NaN poison).

These are pure unit tests — no DB, no fixtures, milliseconds to run.
"""
import pytest
from decimal import Decimal

from app.services.quotation_service import (
    COST_HEAD_COLS,
    DEDUCTED_COST_HEADS,
    sum_cost_heads,
)


pytestmark = pytest.mark.unit


class TestDeductedSet:
    """The deducted set is a one-line constant; tests pin it so a careless
    rename in the helper file is caught instantly."""

    def test_deducted_set_is_exactly_cd_and_spldisc(self):
        assert DEDUCTED_COST_HEADS == frozenset({"CD", "SplDisc"})

    def test_deducted_heads_are_subset_of_all_cost_heads(self):
        assert DEDUCTED_COST_HEADS.issubset(set(COST_HEAD_COLS))


class TestSumCostHeadsDict:
    """sum_cost_heads on dict inputs (the API-layer shape — cost_data
    dicts coming off from-enquiry imports)."""

    def test_only_positive_heads(self):
        result = sum_cost_heads({"TPWGST": 100, "Marketing": 50, "OHD": 25})
        assert result == 175.0
        assert isinstance(result, float)

    def test_only_deducted_heads_subtract(self):
        result = sum_cost_heads({"CD": 30, "SplDisc": 20})
        assert result == -50.0

    def test_mix_of_positive_and_deducted(self):
        # 100 + 50 - 30 - 20 = 100
        result = sum_cost_heads({
            "TPWGST": 100, "Marketing": 50, "CD": 30, "SplDisc": 20,
        })
        assert result == 100.0

    def test_decimal_in_decimal_out(self):
        result = sum_cost_heads({
            "TPWGST": Decimal("100"), "CD": Decimal("30"),
        })
        assert result == Decimal("70")
        assert isinstance(result, Decimal)

    def test_empty_input_returns_zero_float(self):
        # No values → defaults to float 0.0 (use_decimal never flipped).
        result = sum_cost_heads({})
        assert result == 0.0
        assert isinstance(result, float)

    def test_none_values_are_skipped(self):
        result = sum_cost_heads({
            "TPWGST": 100, "Marketing": None, "CD": None,
        })
        assert result == 100.0

    def test_unknown_keys_are_ignored(self):
        # sum_cost_heads only walks COST_HEAD_COLS — stray keys ignored.
        result = sum_cost_heads({
            "TPWGST": 100, "NotARealHead": 9999, "FooBar": "garbage",
        })
        assert result == 100.0

    def test_first_decimal_value_promotes_total(self):
        # First non-None value decides numeric mode. If TPWGST comes in
        # as Decimal, subsequent floats get coerced via Decimal(str(v))
        # to avoid float-precision drift.
        result = sum_cost_heads({
            "TPWGST": Decimal("100.50"), "Marketing": 50.25, "CD": 30.10,
        })
        assert isinstance(result, Decimal)
        # 100.50 + 50.25 - 30.10 = 120.65
        assert result == Decimal("120.65")


class TestSumCostHeadsORMShape:
    """sum_cost_heads on an ORM-like object (the service-layer shape —
    QuotViabilityLine / QuotDetails passing through). We don't need a
    real ORM here; a dataclass with getattr semantics is identical."""

    def _make_row(self, **kwargs):
        class _Row:
            pass
        row = _Row()
        for k in COST_HEAD_COLS:
            setattr(row, k, kwargs.get(k))
        return row

    def test_orm_object_via_getattr(self):
        row = self._make_row(TPWGST=Decimal("50000"), Marketing=Decimal("500"))
        assert sum_cost_heads(row) == Decimal("50500")

    def test_orm_object_with_deducted_heads(self):
        row = self._make_row(
            TPWGST=Decimal("50000"),
            Marketing=Decimal("500"),
            CD=Decimal("100"),
            SplDisc=Decimal("50"),
        )
        # 50000 + 500 - 100 - 50 = 50350
        assert sum_cost_heads(row) == Decimal("50350")

    def test_orm_object_all_none_returns_zero(self):
        row = self._make_row()
        # Every cost head is None → use_decimal never sets → returns float 0.0.
        result = sum_cost_heads(row)
        assert result == 0.0
