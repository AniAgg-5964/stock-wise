"""Validate demand inputs before forecasting (pure, no I/O).

The PRD's data-preparation rules (7.5) require us to check dates, duplicates and
negative quantities before a series is trusted. We report issues rather than
raise, so the UI can still show an "insufficient data" state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence


@dataclass(frozen=True)
class ValidationIssue:
    """A single problem found in a demand series."""

    field: str
    message: str
    row: int | None = None

    def __str__(self) -> str:  # pragma: no cover - display helper
        where = f"row {self.row}: " if self.row is not None else ""
        return f"{where}{self.field} \u2014 {self.message}"


def parse_iso_date(value) -> date | None:
    """Parse ``YYYY-MM-DD`` (ignoring any time part); ``None`` when invalid."""
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def validate_demand_points(points: Sequence[tuple[str, float]]) -> list[ValidationIssue]:
    """Return issues for a sequence of ``(date_str, quantity)`` pairs."""
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for i, (raw_date, raw_qty) in enumerate(points):
        parsed = parse_iso_date(raw_date)
        if parsed is None:
            issues.append(ValidationIssue("demand_date", f"unparseable date {raw_date!r}", i))
            continue
        key = parsed.isoformat()
        if key in seen:
            issues.append(ValidationIssue("demand_date", f"duplicate date {key}", i))
        seen.add(key)
        try:
            qty = float(raw_qty)
        except (TypeError, ValueError):
            issues.append(ValidationIssue("quantity_sold", f"non-numeric quantity {raw_qty!r}", i))
            continue
        if qty < 0:
            issues.append(ValidationIssue("quantity_sold", "negative demand", i))
    return issues


def summarize(points: Sequence[tuple[str, float]]) -> dict:
    """A small, UI-friendly summary of a demand series."""
    return {
        "points": len(points),
        "issues": len(validate_demand_points(points)),
        "first_date": min((str(p[0]) for p in points), default=None),
        "last_date": max((str(p[0]) for p in points), default=None),
    }
