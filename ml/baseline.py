"""Deterministic baseline forecasts (pure).

These serve two roles: they are the transparent fallback when no trained model
is available, and they are the number the XGBoost model must beat before it is
adopted (PRD 7.1, 7.3).
"""

from __future__ import annotations

from typing import Sequence


def _clamp(value: float) -> float:
    """Demand is non-negative (PRD 7.2)."""
    return value if value > 0 else 0.0


def mean_forecast(history: Sequence[float], horizon: int) -> list[float]:
    """Flat forecast at the mean of the history."""
    values = [float(v) for v in history if v is not None]
    avg = sum(values) / len(values) if values else 0.0
    return [_clamp(avg) for _ in range(horizon)]


def moving_average(history: Sequence[float], horizon: int, window: int = 7) -> list[float]:
    """Flat forecast at the mean of the most recent ``window`` days."""
    values = [float(v) for v in history]
    recent = values[-window:] if window > 0 else values
    avg = sum(recent) / len(recent) if recent else 0.0
    return [_clamp(avg) for _ in range(horizon)]


def seasonal_naive(history: Sequence[float], horizon: int, season: int = 7) -> list[float]:
    """Weekday baseline: ``yhat[t] = y[t - season]``.

    Beyond the observed history the model reuses its own prediction from
    ``season`` days earlier, which is the standard recursive seasonal-naive
    extension.
    """
    series = [float(v) for v in history]
    n = len(series)
    out: list[float] = []
    for h in range(horizon):
        idx = n - season + h
        if 0 <= idx < n:
            out.append(_clamp(series[idx]))
        elif h - season >= 0:
            out.append(_clamp(out[h - season]))
        elif series:
            out.append(_clamp(series[-1]))
        else:
            out.append(0.0)
    return out


# Methods exposed to the service/UI, in preference order for the fallback path.
BASELINE_METHODS = {
    "seasonal_naive": seasonal_naive,
    "moving_average": moving_average,
    "mean": mean_forecast,
}

BASELINE_LABELS = {
    "seasonal_naive": "Seasonal naive (same weekday last week)",
    "moving_average": "7-day moving average",
    "mean": "Average demand",
}


def forecast(method: str, history: Sequence[float], horizon: int) -> list[float]:
    """Dispatch to a named baseline; defaults to seasonal-naive."""
    fn = BASELINE_METHODS.get(method, seasonal_naive)
    return fn(history, horizon)
