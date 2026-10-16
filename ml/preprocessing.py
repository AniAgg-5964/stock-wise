"""Turn raw demand rows into a clean, contiguous daily series (pure).

Rule (documented, per PRD 7.5): a missing calendar day is inserted with quantity
``0`` and ``observed=False`` so a genuine zero-sales day can be told apart from a
gap in the data.

A third state is tracked: a day the shop was **out of stock** (``stockout=True``).
Sales were capped by availability on such a day, so recorded units understate real
demand; :func:`impute_censored` replaces them with an estimate before model
training so a stockout is never learned as a genuine drop in demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Collection, Sequence

from ml.data_validation import parse_iso_date


@dataclass(frozen=True)
class DayPoint:
    """One calendar day of demand for a single product."""

    date: str
    quantity: float
    observed: bool = True
    stockout: bool = False
    imputed: bool = False


def to_daily_series(
    points: Sequence[tuple[str, float]],
    *,
    end: str | None = None,
    stockout_dates: Collection[str] | None = None,
) -> list[DayPoint]:
    """Return a contiguous oldest\u2192newest daily series, gap-filled with 0.

    ``end`` extends the grid to that date (inclusive) so a forecast can be made
    even when the most recent days have no sales rows at all. ``stockout_dates``
    marks the days the item was unavailable, so the series carries the censoring
    information the model needs.
    """
    out_of_stock = set(stockout_dates or ())
    cleaned: dict[str, float] = {}
    for raw_date, raw_qty in points:
        parsed = parse_iso_date(raw_date)
        if parsed is None:
            continue
        try:
            qty = float(raw_qty)
        except (TypeError, ValueError):
            continue
        cleaned[parsed.isoformat()] = max(0.0, qty)

    if not cleaned and end is None:
        return []

    first = date.fromisoformat(min(cleaned)) if cleaned else date.fromisoformat(str(end)[:10])
    last = date.fromisoformat(max(cleaned)) if cleaned else date.fromisoformat(str(end)[:10])
    if end is not None:
        end_d = parse_iso_date(end)
        if end_d is not None and (not cleaned or end_d > last):
            last = end_d

    series: list[DayPoint] = []
    cursor = first
    while cursor <= last:
        key = cursor.isoformat()
        if key in cleaned:
            series.append(DayPoint(key, cleaned[key], True, key in out_of_stock))
        else:
            series.append(DayPoint(key, 0.0, False, key in out_of_stock))
        cursor += timedelta(days=1)
    return series


def impute_censored(series: Sequence[DayPoint]) -> list[DayPoint]:
    """Replace out-of-stock (censored) days with an estimate of true demand.

    On a day the shelf was empty, units sold understate demand. Each such day is
    replaced with the mean of the same weekday on non-censored observed days
    (falling back to the overall observed mean) and never below the units that did
    sell. The ``stockout`` flag is kept and ``imputed`` is set so the correction is
    auditable. Days without a stockout are returned untouched.
    """
    if not any(p.stockout for p in series):
        return list(series)

    observed = [p for p in series if p.observed and not p.stockout]
    if not observed:
        return list(series)

    overall = sum(p.quantity for p in observed) / len(observed)
    by_weekday: dict[int, list[float]] = {}
    for point in observed:
        parsed = parse_iso_date(point.date)
        if parsed is not None:
            by_weekday.setdefault(parsed.weekday(), []).append(point.quantity)

    out: list[DayPoint] = []
    for point in series:
        if not point.stockout:
            out.append(point)
            continue
        parsed = parse_iso_date(point.date)
        peers = by_weekday.get(parsed.weekday()) if parsed is not None else None
        estimate = sum(peers) / len(peers) if peers else overall
        out.append(DayPoint(point.date, max(point.quantity, estimate), point.observed, True, True))
    return out


def quantities(series: Sequence[DayPoint]) -> list[float]:
    """Quantities only, oldest\u2192newest."""
    return [p.quantity for p in series]


def observed_count(series: Sequence[DayPoint]) -> int:
    return sum(1 for p in series if p.observed)


def recent_average(series: Sequence[DayPoint], window: int = 28) -> float:
    """Mean demand over the most recent ``window`` observed days."""
    values = [p.quantity for p in series if p.observed][-window:]
    return sum(values) / len(values) if values else 0.0
