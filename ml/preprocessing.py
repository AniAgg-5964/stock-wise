"""Turn raw demand rows into a clean, contiguous daily series (pure).

Rule (documented, per PRD 7.5): a missing calendar day is inserted with quantity
``0`` and ``observed=False`` so a genuine zero-sales day can be told apart from a
gap in the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from ml.data_validation import parse_iso_date


@dataclass(frozen=True)
class DayPoint:
    """One calendar day of demand for a single product."""

    date: str
    quantity: float
    observed: bool = True


def to_daily_series(
    points: Sequence[tuple[str, float]],
    *,
    end: str | None = None,
) -> list[DayPoint]:
    """Return a contiguous oldest\u2192newest daily series, gap-filled with 0.

    ``end`` extends the grid to that date (inclusive) so a forecast can be made
    even when the most recent days have no sales rows at all.
    """
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
            series.append(DayPoint(key, cleaned[key], True))
        else:
            series.append(DayPoint(key, 0.0, False))
        cursor += timedelta(days=1)
    return series


def quantities(series: Sequence[DayPoint]) -> list[float]:
    """Quantities only, oldest\u2192newest."""
    return [p.quantity for p in series]


def observed_count(series: Sequence[DayPoint]) -> int:
    return sum(1 for p in series if p.observed)


def recent_average(series: Sequence[DayPoint], window: int = 28) -> float:
    """Mean demand over the most recent ``window`` observed days."""
    values = [p.quantity for p in series if p.observed][-window:]
    return sum(values) / len(values) if values else 0.0
