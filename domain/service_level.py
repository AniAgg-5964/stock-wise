"""StockWise — service level to safety-factor mapping (pure).

A statistical safety-stock policy needs the normal quantile ``z`` for a target
service level. StockWise ships a small lookup table instead of pulling in SciPy so
the calculation stays dependency-free, offline and reproducible. Values are the
standard normal quantiles rounded to two decimals.
"""

from __future__ import annotations

DEFAULT_SERVICE_LEVEL = 0.90

# Target cycle-service level -> z (standard normal quantile).
SERVICE_LEVEL_Z: dict[float, float] = {
    0.50: 0.00,
    0.60: 0.25,
    0.70: 0.52,
    0.75: 0.67,
    0.80: 0.84,
    0.85: 1.04,
    0.90: 1.28,
    0.92: 1.41,
    0.95: 1.65,
    0.97: 1.88,
    0.98: 2.05,
    0.99: 2.33,
}


def supported_service_levels() -> list[float]:
    """The service levels the UI may offer, ascending."""
    return sorted(SERVICE_LEVEL_Z)


def parse_service_level(value, default: float = DEFAULT_SERVICE_LEVEL) -> float:
    """Normalise a stored setting to a fraction in ``(0, 1]``.

    Accepts ``"0.90"``, ``"90"`` and ``"90%"``; anything unparseable falls back to
    ``default`` so a bad setting can never crash a recommendation.
    """
    if value is None:
        return default
    try:
        text = str(value).strip().rstrip("%")
        parsed = float(text)
    except (TypeError, ValueError):
        return default
    if parsed > 1.0:
        parsed = parsed / 100.0
    if parsed <= 0.0:
        return default
    return min(parsed, 1.0)


def z_for_service_level(level, default: float = DEFAULT_SERVICE_LEVEL) -> float:
    """Return the tabulated ``z`` nearest to ``level`` (clamped to the table)."""
    parsed = parse_service_level(level, default)
    levels = sorted(SERVICE_LEVEL_Z)
    clamped = min(max(parsed, levels[0]), levels[-1])
    nearest = min(levels, key=lambda candidate: abs(candidate - clamped))
    return SERVICE_LEVEL_Z[nearest]
