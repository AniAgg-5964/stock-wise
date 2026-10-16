"""Forecast accuracy metrics (pure functions).

MAE, RMSE, WAPE and bias per the PRD 7.6 metric table. WAPE is reported as
``None`` when total actual demand is zero (undefined), never as a fake number.
"""

from __future__ import annotations

import math
from typing import Sequence


def _pairs(actual: Sequence[float], predicted: Sequence[float]) -> list[tuple[float, float]]:
    n = min(len(actual), len(predicted))
    return [(float(actual[i]), float(predicted[i])) for i in range(n)]


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Mean absolute error in units."""
    pairs = _pairs(actual, predicted)
    return sum(abs(a - p) for a, p in pairs) / len(pairs) if pairs else 0.0


def rmse(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Root mean squared error; penalises large misses."""
    pairs = _pairs(actual, predicted)
    if not pairs:
        return 0.0
    return math.sqrt(sum((a - p) ** 2 for a, p in pairs) / len(pairs))


def wape(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    """Weighted absolute percentage error; ``None`` when total demand is zero."""
    pairs = _pairs(actual, predicted)
    total = sum(a for a, _ in pairs)
    if not pairs or total == 0:
        return None
    return 100.0 * sum(abs(a - p) for a, p in pairs) / total


def bias(actual: Sequence[float], predicted: Sequence[float]) -> float:
    """Signed error: positive = over-forecast, negative = under-forecast."""
    pairs = _pairs(actual, predicted)
    return sum(p - a for a, p in pairs) / len(pairs) if pairs else 0.0


def metrics(actual: Sequence[float], predicted: Sequence[float]) -> dict:
    """All metrics at once (numbers only; safe to JSON-encode)."""
    return {
        "mae": mae(actual, predicted),
        "rmse": rmse(actual, predicted),
        "wape": wape(actual, predicted),
        "bias": bias(actual, predicted),
        "n": min(len(actual), len(predicted)),
    }


def format_wape(value: float | None) -> str:
    """Human label for WAPE, including the explicitly-undefined case."""
    return "n/a (zero demand)" if value is None else f"{value:.1f}%"
