"""Prediction-interval helper for the recursive multi-step forecast (pure).

The forecast is produced one day at a time, so errors accumulate with the horizon.
The half-width for step ``h`` (1-based) is therefore ``z * sigma * sqrt(h)`` — the
standard random-walk variance accumulation — where ``sigma`` is the model's or
baseline's holdout residual standard deviation.

Intervals are only meaningful when variability has actually been estimated; a zero
``sigma`` yields a zero-width interval, and the caller stores ``None`` bounds
instead of pretending the forecast is certain.
"""

from __future__ import annotations

import math
from typing import Sequence

DEFAULT_Z = 1.28  # ~90% service level


def interval_bounds(
    predicted: Sequence[float],
    residual_std: float,
    *,
    z: float = DEFAULT_Z,
) -> tuple[list[float], list[float]]:
    """Return ``(lowers, uppers)`` for ``predicted``; demand is never negative."""
    sigma = max(0.0, float(residual_std or 0.0))
    factor = max(0.0, float(z))
    lowers: list[float] = []
    uppers: list[float] = []
    for step, value in enumerate(predicted, start=1):
        half_width = factor * sigma * math.sqrt(step)
        point = float(value)
        lowers.append(max(0.0, point - half_width))
        uppers.append(point + half_width)
    return lowers, uppers
