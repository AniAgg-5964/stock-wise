"""Leakage-safe feature engineering for the forecasting model (PRD 7.4).

Every feature for a target day uses only information available *before* that day
(shifted lags and rolling windows), so the model can never peek at the future.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

import numpy as np

from ml.preprocessing import DayPoint

FEATURE_SCHEMA_VERSION = "1"
MIN_LAG = 28

FEATURE_NAMES: list[str] = [
    "lag_1",
    "lag_7",
    "lag_14",
    "lag_28",
    "rolling_mean_7",
    "rolling_mean_28",
    "rolling_std_28",
    "day_of_week",
    "is_weekend",
    "day_of_month",
    "month",
    "product_code",
]


def feature_row(values: Sequence[float], product_code: int, day: date) -> list[float]:
    """Features for ``day`` from ``values`` (history strictly before ``day``)."""
    window = [float(v) for v in values[-MIN_LAG:]]
    if len(window) < MIN_LAG:
        window = [0.0] * (MIN_LAG - len(window)) + window

    lag_1, lag_7, lag_14, lag_28 = window[-1], window[-7], window[-14], window[-28]
    mean_7 = sum(window[-7:]) / 7
    mean_28 = sum(window) / MIN_LAG
    var_28 = sum((v - mean_28) ** 2 for v in window) / MIN_LAG
    dow = day.weekday()
    return [
        lag_1,
        lag_7,
        lag_14,
        lag_28,
        mean_7,
        mean_28,
        math.sqrt(var_28),
        float(dow),
        1.0 if dow >= 5 else 0.0,
        float(day.day),
        float(day.month),
        float(product_code),
    ]


@dataclass
class FeatureMatrix:
    X: np.ndarray
    y: np.ndarray
    dates: list[str]
    product_ids: list[int]
    feature_names: list[str]


def build_matrix(
    series_by_product: Mapping[int, Sequence[DayPoint]],
    *,
    min_history: int = MIN_LAG,
    date_before: str | None = None,
    date_from: str | None = None,
) -> FeatureMatrix:
    """Build a supervised matrix from one or more product series.

    ``date_before`` / ``date_from`` restrict which target days are included, which
    is how the chronological train/holdout split is enforced.
    """
    rows: list[list[float]] = []
    targets: list[float] = []
    dates: list[str] = []
    product_ids: list[int] = []

    for product_id, series in series_by_product.items():
        values = [p.quantity for p in series]
        for idx in range(min_history, len(series)):
            day_str = series[idx].date
            if date_before is not None and day_str >= date_before:
                continue
            if date_from is not None and day_str < date_from:
                continue
            rows.append(feature_row(values[:idx], product_id, date.fromisoformat(day_str)))
            targets.append(values[idx])
            dates.append(day_str)
            product_ids.append(product_id)

    X = np.array(rows, dtype=float) if rows else np.zeros((0, len(FEATURE_NAMES)), dtype=float)
    y = np.array(targets, dtype=float)
    return FeatureMatrix(X, y, dates, product_ids, list(FEATURE_NAMES))


def split_dates(series_by_product: Mapping[int, Sequence[DayPoint]], horizon: int) -> tuple[str, list[str]]:
    """Return ``(test_start, test_dates)`` for a chronological split."""
    all_dates = sorted({p.date for series in series_by_product.values() for p in series})
    if len(all_dates) <= horizon:
        raise ValueError("Not enough distinct dates to hold out a test window.")
    test_dates = all_dates[-horizon:]
    return test_dates[0], test_dates
