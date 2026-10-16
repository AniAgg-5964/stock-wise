"""StockWise — periodic-review replenishment engine (pure business logic).

Deterministic and side-effect free: the same inputs always produce the same
recommendation (PRD 8). No I/O, no ML, no SQL.

Policy (PRD 8.2 / 8.3):
    P          = L + R                          protection period
    mu_P       = sum(forecast[d] for d in next P days)
    S          = mu_P + SS_P                    order-up-to target
    IP         = usable on-hand + confirmed incoming - commitments (- at-risk)
    Q_raw      = max(0, S - IP)
    order_qty  = round_up_to_pack(max(Q_raw, MOQ))   # only when Q_raw > 0
    then re-check against budget (never silently exceed it)

Worked fixture (PRD): L=3, R=2 -> P=5; forecasts [8,10,9,12,11] sum 50;
SS=6 -> S=56; IP=36 -> Q_raw=20; budget 1000/70 -> cap 14, shortfall 6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

# Urgency labels (also used as the colour key in the UI).
URGENCY_CRITICAL = "critical"
URGENCY_HIGH = "high"
URGENCY_MEDIUM = "medium"
URGENCY_LOW = "low"


@dataclass
class ReorderContext:
    """All inputs to a single reorder decision (already resolved by the service)."""

    product_id: int
    product_name: str
    unit: str
    forecast: Sequence[float]            # daily forecasts, starting tomorrow
    avg_daily_demand: float
    usable_on_hand: float
    lead_time_days: int
    review_period_days: int
    safety_stock: float                  # resolved SS_P for the protection period
    confirmed_incoming: float = 0.0
    commitments: float = 0.0
    at_risk_expiry: float = 0.0
    minimum_order_qty: int = 1
    pack_size: int = 1
    unit_cost: Decimal = Decimal("0")
    budget: Decimal | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None


@dataclass
class ReorderRecommendation:
    """A fully-explained replenishment suggestion (advisory only)."""

    product_id: int
    product_name: str
    unit: str
    suggested_qty: int
    estimated_cost: Decimal
    urgency: str

    protection_period_days: int
    lead_time_days: int
    review_period_days: int
    lead_time_demand: float
    review_period_demand: float
    forecast_period_demand: float
    safety_stock: float
    target_position: float
    usable_on_hand: float
    at_risk_expiry: float
    confirmed_incoming: float
    commitments: float
    inventory_position: float
    raw_qty: float

    minimum_order_qty: int = 1
    pack_size: int = 1
    unit_cost: Decimal = Decimal("0")
    budget: Decimal | None = None
    budget_capped_qty: int | None = None
    shortfall: int = 0
    supplier_id: int | None = None
    supplier_name: str | None = None
    days_to_stockout: float | None = None
    expiry_review_required: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def needs_order(self) -> bool:
        return self.suggested_qty > 0

    def rationale(self) -> dict:
        """JSON-serialisable explanation for the database / UI."""
        return {
            "protection_period_days": self.protection_period_days,
            "lead_time_days": self.lead_time_days,
            "review_period_days": self.review_period_days,
            "forecast_period_demand": round(self.forecast_period_demand, 3),
            "lead_time_demand": round(self.lead_time_demand, 3),
            "review_period_demand": round(self.review_period_demand, 3),
            "safety_stock": round(self.safety_stock, 3),
            "target_position": round(self.target_position, 3),
            "inventory_position": round(self.inventory_position, 3),
            "usable_on_hand": round(self.usable_on_hand, 3),
            "at_risk_expiry": round(self.at_risk_expiry, 3),
            "confirmed_incoming": round(self.confirmed_incoming, 3),
            "commitments": round(self.commitments, 3),
            "raw_qty": round(self.raw_qty, 3),
            "suggested_qty": self.suggested_qty,
            "minimum_order_qty": self.minimum_order_qty,
            "pack_size": self.pack_size,
            "unit_cost": str(self.unit_cost),
            "budget": None if self.budget is None else str(self.budget),
            "budget_capped_qty": self.budget_capped_qty,
            "shortfall": self.shortfall,
            "days_to_stockout": None if self.days_to_stockout is None else round(self.days_to_stockout, 2),
            "urgency": self.urgency,
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------- helpers
def protection_period(lead_time_days: int, review_period_days: int) -> int:
    return max(0, int(lead_time_days)) + max(0, int(review_period_days))


def demand_over_period(forecast: Sequence[float], days: int) -> float:
    """Sum the next ``days`` forecasts, padding short series with their mean."""
    days = max(0, int(days))
    values = [float(v) for v in forecast]
    if days == 0:
        return 0.0
    if not values:
        return 0.0
    if len(values) >= days:
        return sum(values[:days])
    mean = sum(values) / len(values)
    return sum(values) + mean * (days - len(values))


def safety_stock_heuristic(
    avg_daily_demand: float,
    safety_buffer_days: int,
    configured_minimum: float = 0.0,
) -> float:
    """Simple policy: ``max(configured_minimum, average_daily_demand * buffer_days)``."""
    return max(float(configured_minimum), float(avg_daily_demand) * max(0, int(safety_buffer_days)))


def safety_stock_statistical(
    residual_std: float,
    protection_days: int,
    z: float = 1.28,
) -> float:
    """Statistical approximation: ``SS = z * sigma_P`` with ``sigma_P = std * sqrt(P)``.

    Only meaningful when demand variability has actually been estimated; the UI
    labels this as a statistical policy rather than a heuristic.
    """
    sigma_p = max(0.0, float(residual_std)) * math.sqrt(max(0, int(protection_days)))
    return max(0.0, float(z)) * sigma_p


def inventory_position(
    usable_on_hand: float,
    confirmed_incoming: float = 0.0,
    commitments: float = 0.0,
    at_risk_expiry: float = 0.0,
) -> float:
    """Usable position available to meet upcoming demand."""
    return float(usable_on_hand) + float(confirmed_incoming) - float(commitments) - float(at_risk_expiry)


def raw_order_qty(target_position_value: float, position: float) -> float:
    return max(0.0, float(target_position_value) - float(position))


def urgency(days_to_stockout: float | None, lead_time_days: int, review_period_days: int) -> str:
    if days_to_stockout is None:
        return URGENCY_LOW
    if days_to_stockout <= 0:
        return URGENCY_CRITICAL
    if days_to_stockout <= max(0, lead_time_days):
        return URGENCY_HIGH
    if days_to_stockout <= protection_period(lead_time_days, review_period_days):
        return URGENCY_MEDIUM
    return URGENCY_LOW


def apply_constraints(
    raw_qty: float,
    *,
    minimum_order_qty: int = 1,
    pack_size: int = 1,
    unit_cost: Decimal = Decimal("0"),
    budget: Decimal | None = None,
) -> tuple[int, int | None, int, list[str]]:
    """Apply MOQ, pack rounding and budget. Returns ``(qty, cap, shortfall, notes)``."""
    notes: list[str] = []
    moq = max(1, int(minimum_order_qty))
    pack = max(1, int(pack_size))

    if raw_qty <= 0:
        return 0, None, 0, ["Stock already covers demand over the protection period."]

    qty = float(raw_qty)
    if qty < moq:
        qty = float(moq)
        notes.append(f"Raised to the supplier minimum order quantity ({moq}).")

    packs = math.ceil(qty / pack)
    if pack > 1:
        qty = packs * pack
        notes.append(f"Rounded up to a multiple of the pack size ({pack}) \u2192 {int(qty)}.")

    budget_capped: int | None = None
    shortfall = 0
    if budget is not None and unit_cost and Decimal(str(unit_cost)) > 0:
        affordable = int(Decimal(str(budget)) // Decimal(str(unit_cost)))
        if qty > affordable:
            budget_capped = affordable
            shortfall = int(qty - affordable)
            notes.append(
                f"Limited by budget: {affordable} unit(s) affordable; {shortfall} unit(s) deferred."
            )
            if affordable < moq:
                notes.append("Budget cap is below the minimum order quantity \u2014 constraints conflict.")
            qty = float(affordable)

    return int(qty), budget_capped, shortfall, notes


# ----------------------------------------------------------------------- engine
def compute(context: ReorderContext) -> ReorderRecommendation:
    """Run the periodic-review calculation for one product."""
    p = protection_period(context.lead_time_days, context.review_period_days)
    forecasts = list(context.forecast)

    lead_demand = demand_over_period(forecasts, context.lead_time_days)
    review_demand = demand_over_period(forecasts, p) - lead_demand
    period_demand = lead_demand + review_demand

    target = period_demand + float(context.safety_stock)
    position = inventory_position(
        context.usable_on_hand, context.confirmed_incoming, context.commitments, context.at_risk_expiry
    )
    raw = raw_order_qty(target, position)

    qty, budget_capped, shortfall, notes = apply_constraints(
        raw,
        minimum_order_qty=context.minimum_order_qty,
        pack_size=context.pack_size,
        unit_cost=context.unit_cost,
        budget=context.budget,
    )

    days_to_stockout = (
        context.usable_on_hand / context.avg_daily_demand
        if context.avg_daily_demand and context.avg_daily_demand > 0
        else None
    )

    expiry_review = context.at_risk_expiry > 0
    if expiry_review:
        notes.append(
            f"{context.at_risk_expiry:g} {context.unit} may expire before it sells \u2014 "
            "consider markdown or transfer before ordering more."
        )
    if not notes:
        notes.append("Position covers the protection period; no order suggested.")

    estimated_cost = (Decimal(str(context.unit_cost)) * qty).quantize(Decimal("0.01"))

    return ReorderRecommendation(
        product_id=context.product_id,
        product_name=context.product_name,
        unit=context.unit,
        suggested_qty=qty,
        estimated_cost=estimated_cost,
        urgency=urgency(days_to_stockout, context.lead_time_days, context.review_period_days),
        protection_period_days=p,
        lead_time_days=context.lead_time_days,
        review_period_days=context.review_period_days,
        lead_time_demand=lead_demand,
        review_period_demand=review_demand,
        forecast_period_demand=period_demand,
        safety_stock=float(context.safety_stock),
        target_position=target,
        usable_on_hand=context.usable_on_hand,
        at_risk_expiry=context.at_risk_expiry,
        confirmed_incoming=context.confirmed_incoming,
        commitments=context.commitments,
        inventory_position=position,
        raw_qty=raw,
        minimum_order_qty=context.minimum_order_qty,
        pack_size=context.pack_size,
        unit_cost=Decimal(str(context.unit_cost)),
        budget=context.budget,
        budget_capped_qty=budget_capped,
        shortfall=shortfall,
        supplier_id=context.supplier_id,
        supplier_name=context.supplier_name,
        days_to_stockout=days_to_stockout,
        expiry_review_required=expiry_review,
        notes=notes,
    )
