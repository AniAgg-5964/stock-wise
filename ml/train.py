"""Train the XGBoost demand model and compare it honestly against baselines.

Training is an admin/developer operation (PRD 7.9), not part of app startup. The
model is only marked *adopted* when it beats or matches the best baseline on a
chronological holdout (PRD 7.1) \u2014 otherwise the app keeps using the baseline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Mapping, Sequence

from ml import baseline, evaluate
from ml.features import FEATURE_SCHEMA_VERSION, MIN_LAG, build_matrix, split_dates
from ml.preprocessing import DayPoint
from ml.predict import recursive_forecast

logger = logging.getLogger(__name__)

BASELINE_KEYS = ("seasonal_naive", "moving_average", "mean")

# Fixed, reproducible configuration (PRD 7.6: start fixed, use holdout for tuning).
DEFAULT_PARAMS: dict = {
    "n_estimators": 300,
    "max_depth": 4,
    "learning_rate": 0.08,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": 2,
    "objective": "reg:squarederror",
}

MIN_TRAINING_ROWS = 30


@dataclass
class TrainingResult:
    version: str
    adopted: bool
    metrics: dict
    baseline_metrics: dict
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    train_start: str | None = None
    train_end: str | None = None
    test_start: str | None = None
    test_end: str | None = None
    n_train: int = 0
    products: int = 0
    hyperparameters: dict = field(default_factory=dict)
    notes: str = ""


def _history_before(series: Sequence[DayPoint], test_start: str) -> list[float]:
    return [p.quantity for p in series if p.date < test_start]


def _actuals_from(series: Sequence[DayPoint], test_dates: Sequence[str]) -> list[float]:
    by_date = {p.date: p.quantity for p in series}
    return [by_date.get(d, 0.0) for d in test_dates]


def train_global(
    series_by_product: Mapping[int, Sequence[DayPoint]],
    *,
    horizon: int = 7,
    params: dict | None = None,
    version: str | None = None,
) -> tuple[object, TrainingResult]:
    """Train a pooled model; return ``(model, result)``."""
    hyperparameters = {**DEFAULT_PARAMS, **(params or {})}
    test_start, test_dates = split_dates(series_by_product, horizon)

    matrix = build_matrix(series_by_product, date_before=test_start)
    if matrix.X.shape[0] < MIN_TRAINING_ROWS:
        raise ValueError(
            f"Not enough training rows ({matrix.X.shape[0]}); need at least {MIN_TRAINING_ROWS}."
        )

    import xgboost as xgb

    model = xgb.XGBRegressor(**hyperparameters)
    model.fit(matrix.X, matrix.y)

    # ---- chronological holdout: recursive multi-step per product ----
    actual_all: list[float] = []
    predicted_all: list[float] = []
    baseline_preds: dict[str, list[float]] = {k: [] for k in BASELINE_KEYS}
    start_day = date.fromisoformat(test_start)

    for product_id, series in series_by_product.items():
        history = _history_before(series, test_start)
        if len(history) < MIN_LAG:
            continue
        actual = _actuals_from(series, test_dates)
        model_pred = recursive_forecast(
            lambda X, m=model: m.predict(X), history, product_id, start_day, len(test_dates)
        )
        actual_all.extend(actual)
        predicted_all.extend(model_pred)
        for name in BASELINE_KEYS:
            baseline_preds[name].extend(baseline.forecast(name, history, len(test_dates)))

    model_metrics = evaluate.metrics(actual_all, predicted_all)
    baseline_metrics = {name: evaluate.metrics(actual_all, vals) for name, vals in baseline_preds.items()}
    best_baseline = min(
        (m for m in baseline_metrics.values() if m["wape"] is not None),
        key=lambda m: m["wape"],
        default=None,
    )
    adopted = model_metrics["wape"] is not None and (
        best_baseline is None or model_metrics["wape"] <= best_baseline["wape"]
    )

    version = version or datetime.now(timezone.utc).strftime("xgb-%Y%m%d-%H%M%S")
    result = TrainingResult(
        version=version,
        adopted=adopted,
        metrics=model_metrics,
        baseline_metrics=baseline_metrics,
        train_start=matrix.dates[0] if matrix.dates else None,
        train_end=matrix.dates[-1] if matrix.dates else None,
        test_start=test_start,
        test_end=test_dates[-1],
        n_train=int(matrix.X.shape[0]),
        products=len(series_by_product),
        hyperparameters=hyperparameters,
        notes=(
            "Adopted: beats or matches the best baseline on holdout."
            if adopted
            else "Kept as candidate only: did not beat the baseline, so the baseline is used."
        ),
    )
    return model, result
