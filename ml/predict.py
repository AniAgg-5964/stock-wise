"""Forecast inference and fallback selection (PRD 7.3, 7.7).

``recursive_forecast`` is the multi-step forecasting routine used both for
holdout evaluation and for production inference: predict one day, append it to
the history, then predict the next. Any failure is surfaced to the caller so the
service can fall back to a transparent baseline.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Sequence

import numpy as np

from ml.features import feature_row


def recursive_forecast(
    predict_one: Callable[[np.ndarray], np.ndarray],
    history: Sequence[float],
    product_code: int,
    start_day: date,
    horizon: int,
) -> list[float]:
    """Forecast ``horizon`` days from ``start_day`` using only ``history``."""
    values = [float(v) for v in history]
    out: list[float] = []
    day = start_day
    for _ in range(horizon):
        row = feature_row(values, product_code, day)
        predicted = float(predict_one(np.array([row], dtype=float))[0])
        predicted = predicted if predicted > 0 else 0.0  # non-negative demand
        out.append(predicted)
        values.append(predicted)
        day += timedelta(days=1)
    return out
