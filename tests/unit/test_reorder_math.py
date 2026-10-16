"""Unit tests for the pure periodic-review reorder math (PRD 8)."""

from __future__ import annotations

from decimal import Decimal

from domain.reorder import (
    ReorderContext,
    apply_constraints,
    compute,
    demand_over_period,
    inventory_position,
    protection_period,
    safety_stock_heuristic,
    safety_stock_statistical,
    urgency,
)


def _context(**overrides) -> ReorderContext:
    base = dict(
        product_id=1,
        product_name="Test Item",
        unit="pcs",
        forecast=[8, 10, 9, 12, 11],
        avg_daily_demand=10.0,
        usable_on_hand=36.0,
        lead_time_days=3,
        review_period_days=2,
        safety_stock=6.0,
        minimum_order_qty=1,
        pack_size=1,
        unit_cost=Decimal("70"),
        budget=Decimal("1000"),
    )
    base.update(overrides)
    return ReorderContext(**base)


class TestHelpers:
    def test_protection_period(self):
        assert protection_period(3, 2) == 5

    def test_demand_over_period_sums_and_pads(self):
        assert demand_over_period([8, 10, 9, 12, 11], 5) == 50
        # padded with the mean when the forecast is shorter than the period
        assert demand_over_period([4, 6], 4) == 20

    def test_safety_stock_heuristic(self):
        assert safety_stock_heuristic(10, 2, configured_minimum=5) == 20
        assert safety_stock_heuristic(10, 2, configured_minimum=30) == 30

    def test_safety_stock_statistical(self):
        assert round(safety_stock_statistical(4, 5, z=1.28), 2) == round(1.28 * 4 * (5 ** 0.5), 2)

    def test_inventory_position(self):
        assert inventory_position(30, confirmed_incoming=10, commitments=2, at_risk_expiry=2) == 36

    def test_urgency(self):
        assert urgency(0, 3, 2) == "critical"
        assert urgency(2, 3, 2) == "high"
        assert urgency(4, 3, 2) == "medium"
        assert urgency(50, 3, 2) == "low"


class TestConstraints:
    def test_budget_cap_and_shortfall(self):
        qty, cap, shortfall, notes = apply_constraints(
            20, minimum_order_qty=1, pack_size=1, unit_cost=Decimal("70"), budget=Decimal("1000")
        )
        assert (qty, cap, shortfall) == (14, 14, 6)
        assert any("budget" in n.lower() for n in notes)

    def test_moq_only_applied_when_order_needed(self):
        qty, _, _, notes = apply_constraints(0, minimum_order_qty=10, pack_size=5)
        assert qty == 0
        assert any("covers demand" in n for n in notes)

    def test_pack_rounding(self):
        qty, _, _, _ = apply_constraints(7, minimum_order_qty=1, pack_size=6)
        assert qty == 12

    def test_budget_below_moq_is_flagged(self):
        _, _, _, notes = apply_constraints(
            20, minimum_order_qty=10, pack_size=1, unit_cost=Decimal("100"), budget=Decimal("500")
        )
        assert any("conflict" in n.lower() for n in notes)


class TestFixture:
    """The worked example from the PRD / implementation plan."""

    def test_matches_hand_calculation(self):
        reco = compute(_context())

        assert reco.protection_period_days == 5
        assert reco.forecast_period_demand == 50
        assert reco.safety_stock == 6
        assert reco.target_position == 56
        assert reco.inventory_position == 36
        assert reco.raw_qty == 20
        assert reco.suggested_qty == 14          # budget-capped from 20
        assert reco.budget_capped_qty == 14
        assert reco.shortfall == 6
        assert reco.estimated_cost == Decimal("980.00")

    def test_no_order_when_position_covers_target(self):
        reco = compute(_context(usable_on_hand=100.0))
        assert reco.suggested_qty == 0
        assert reco.needs_order is False

    def test_incoming_stock_reduces_order(self):
        without = compute(_context())
        with_incoming = compute(_context(confirmed_incoming=10.0))
        assert with_incoming.raw_qty == without.raw_qty - 10

    def test_at_risk_expiry_raises_order_and_flags_review(self):
        reco = compute(_context(at_risk_expiry=5.0))
        assert reco.expiry_review_required is True
        assert reco.raw_qty == 25
        assert any("expire" in n.lower() for n in reco.notes)

    def test_zero_demand_is_handled(self):
        reco = compute(_context(forecast=[0, 0, 0, 0, 0], avg_daily_demand=0.0,
                                usable_on_hand=0.0, safety_stock=0.0))
        assert reco.suggested_qty == 0
        assert reco.days_to_stockout is None
