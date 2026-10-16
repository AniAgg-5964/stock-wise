"""StockWise — forecasting service.

Orchestrates the ML pipeline: pull demand history from the repository, build a
clean daily series, produce a forecast (a trained model when available, otherwise
a transparent baseline), persist it, and expose backtest metrics.

Forecasting never mutates stock and never raises for missing data \u2014 it returns an
``insufficient_data`` result instead so the UI can be honest.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.config import Config
from application.dto import ForecastMetrics, ForecastPoint, ForecastResult
from domain.exceptions import NotFoundError, StockWiseError
from ml import baseline as baselines
from ml import evaluate as eval_metrics
from ml.features import FEATURE_SCHEMA_VERSION
from ml.preprocessing import DayPoint, observed_count, quantities, recent_average, to_daily_series


class ForecastService:
    def __init__(self, db, forecast_repo, product_repo, settings_repo=None, model_service=None) -> None:
        self.db = db
        self.forecasts = forecast_repo
        self.products = product_repo
        self.settings = settings_repo
        self.model_service = model_service

    # ------------------------------------------------------------------- config
    def _horizon(self, override: int | None = None) -> int:
        if override is not None and override > 0:
            return int(override)
        if self.settings is not None:
            value = self.settings.get("forecast_horizon_days")
            if value:
                try:
                    parsed = int(value)
                    if parsed > 0:
                        return parsed
                except (TypeError, ValueError):
                    pass
        return Config.DEFAULT_FORECAST_HORIZON

    def _baseline_method(self, override: str | None = None) -> str:
        if override:
            return override
        if self.settings is not None:
            value = self.settings.get("forecast_baseline_method")
            if value in baselines.BASELINE_METHODS:
                return value
        return "seasonal_naive"

    # -------------------------------------------------------------------- reads
    def demand_series(self, product_id: int, *, end: str | None = None) -> list[DayPoint]:
        """The product's demand as a contiguous daily grid (oldest\u2192newest)."""
        end = end or date.today().isoformat()
        history = self.forecasts.get_demand_history(product_id)
        return to_daily_series(history, end=end)

    def average_daily_demand(self, product_id: int, *, window: int = 28) -> float:
        return recent_average(self.demand_series(product_id), window)

    # --------------------------------------------------------- forecast writing
    def generate(
        self,
        product_id: int,
        *,
        horizon: int | None = None,
        method: str = "auto",
    ) -> ForecastResult:
        """Produce, persist and return a forecast for one product."""
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)

        horizon = self._horizon(horizon)
        today = date.today()
        series = self.demand_series(product_id, end=today.isoformat())
        observed = observed_count(series)
        values = quantities(series)

        insufficient = observed < Config.MIN_TRAINING_DAYS
        note = ""

        chosen = method
        if insufficient:
            chosen = "mean"
            predicted = baselines.mean_forecast(values or [0.0], horizon)
            note = (
                f"Only {observed} day(s) of sales history \u2014 showing average demand. "
                f"At least {Config.MIN_TRAINING_DAYS} days are needed for a reliable forecast."
            )
        else:
            model_prediction = None
            if method in ("auto", "xgboost") and self.model_service is not None:
                model_prediction = self.model_service.predict(
                    product, series, horizon, allow_candidate=(method == "xgboost")
                )
            if model_prediction is not None:
                chosen = "xgboost"
                predicted = model_prediction
            else:
                chosen = self._baseline_method(None if method in ("auto", "xgboost") else method)
                predicted = baselines.forecast(chosen, values, horizon)
                if method == "xgboost":
                    note = "No trained model available \u2014 showing the baseline forecast instead."

        residual_std = self._residual_std(product_id, horizon, chosen)

        points = [
            ForecastPoint(
                target_date=(today + timedelta(days=i + 1)).isoformat(),
                predicted_qty=round(float(qty), 3),
            )
            for i, qty in enumerate(predicted)
        ]

        is_baseline = chosen != "xgboost"
        version = f"baseline:{chosen}" if is_baseline else f"xgboost:{FEATURE_SCHEMA_VERSION}"
        self.forecasts.replace_forecasts(
            product_id,
            [{"target_date": p.target_date, "predicted_qty": p.predicted_qty} for p in points],
            horizon=horizon,
            model_version=version,
            fallback_used=is_baseline,
        )

        return ForecastResult(
            product_id=product_id,
            product_name=product.name,
            horizon=horizon,
            method=chosen,
            method_label=_method_label(chosen),
            generated_at=today.isoformat(),
            is_baseline=is_baseline,
            fallback_used=is_baseline,
            insufficient_data=insufficient,
            average_daily_demand=round(recent_average(series), 3),
            observed_days=observed,
            residual_std=round(residual_std, 3),
            note=note,
            points=points,
        )

    def generate_all(self, *, horizon: int | None = None) -> list[ForecastResult]:
        results: list[ForecastResult] = []
        for product in self.products.list_all(active_only=True):
            results.append(self.generate(product.id, horizon=horizon))
        return results

    # ------------------------------------------------------------ forecast reads
    def latest(self, product_id: int) -> ForecastResult | None:
        """Read the most recently stored forecast (no recomputation)."""
        rows = self.forecasts.get_forecasts(product_id)
        if not rows:
            return None
        product = self.products.get_by_id(product_id)
        version = rows[0].get("model_version") or "baseline:seasonal_naive"
        method, _, _ = _split_version(version)
        return ForecastResult(
            product_id=product_id,
            product_name=product.name if product else f"Product #{product_id}",
            horizon=int(rows[0].get("horizon") or len(rows)),
            method=method,
            method_label=_method_label(method),
            generated_at=rows[0].get("generated_at"),
            is_baseline=bool(rows[0].get("fallback_used")),
            fallback_used=bool(rows[0].get("fallback_used")),
            average_daily_demand=round(self.average_daily_demand(product_id), 3),
            observed_days=observed_count(self.demand_series(product_id)),
            points=[
                ForecastPoint(
                    target_date=r["target_date"],
                    predicted_qty=float(r["predicted_qty"]),
                    lower_bound=r.get("lower_bound"),
                    upper_bound=r.get("upper_bound"),
                )
                for r in rows
            ],
        )

    def forecast_demand(self, product_id: int, days: int) -> tuple[float, ForecastResult]:
        """Demand over the next ``days`` (generating a fresh forecast if needed).

        Used by the reorder engine; returns the summed quantity and the forecast.
        """
        result = self.latest(product_id)
        if result is None or len(result.points) < days:
            result = self.generate(product_id, horizon=max(days, self._horizon()))
        total = sum(p.predicted_qty for p in result.points[:days])
        return round(total, 3), result

    # ----------------------------------------------------------------- backtest
    def backtest(self, product_id: int, *, horizon: int | None = None) -> list[ForecastMetrics]:
        """Chronological holdout evaluation of each baseline (PRD 7.6)."""
        horizon = horizon or self._horizon()
        series = self.demand_series(product_id)
        if len(series) < horizon + Config.MIN_TRAINING_DAYS:
            return []
        train = quantities(series[:-horizon])
        test = quantities(series[-horizon:])

        results: list[ForecastMetrics] = []
        for method in ("seasonal_naive", "moving_average", "mean"):
            predicted = baselines.forecast(method, train, horizon)
            m = eval_metrics.metrics(test, predicted)
            results.append(
                ForecastMetrics(
                    method=method,
                    label=baselines.BASELINE_LABELS[method],
                    mae=m["mae"],
                    rmse=m["rmse"],
                    wape=m["wape"],
                    bias=m["bias"],
                    n=m["n"],
                )
            )
        return results

    # -------------------------------------------------------------- model admin
    def model_status(self) -> dict:
        """Current state of the trained model (present / adopted / metrics)."""
        if self.model_service is None:
            return {"artifact_present": False, "available": False, "adopted": False, "metrics": {},
                    "baseline_metrics": {}, "notes": "", "version": None, "trained_at": None}
        return self.model_service.status()

    def train_model(self, *, horizon: int | None = None, force: bool = False) -> dict:
        """Train the pooled XGBoost model and record the run (admin operation)."""
        if self.model_service is None:
            raise StockWiseError("No model service is configured.")

        horizon = self._horizon(horizon)
        series_by_product = {
            product.id: self.demand_series(product.id)
            for product in self.products.list_all(active_only=True)
        }
        summary = self.model_service.train(series_by_product, horizon=horizon, force=force)
        self.forecasts.create_model_run(
            model_version=summary["version"],
            model_type="xgboost",
            metrics={
                "model": summary.get("metrics", {}),
                "baselines": summary.get("baseline_metrics", {}),
                "adopted": summary.get("adopted", False),
            },
            artifact_path=summary.get("artifact_path"),
            train_start=summary.get("train_start"),
            train_end=summary.get("train_end"),
            feature_schema_version=summary.get("feature_schema_version", FEATURE_SCHEMA_VERSION),
            notes=summary.get("notes"),
        )
        return summary

    # ------------------------------------------------------------------ internal
    def _residual_std(self, product_id: int, horizon: int, method: str) -> float:
        """RMSE from the last holdout window, used as a sigma proxy for safety stock."""
        for metric in self.backtest(product_id, horizon=horizon):
            if metric.method == method:
                return metric.rmse
        return 0.0


def _split_version(version: str) -> tuple[str, str, str]:
    """``"baseline:seasonal_naive"`` \u2192 ``("seasonal_naive", "baseline", ...)``."""
    kind, _, name = version.partition(":")
    if kind == "baseline":
        return (name or "seasonal_naive", "baseline", name)
    if kind == "xgboost":
        return ("xgboost", "xgboost", name)
    return (version, "", "")


def _method_label(method: str) -> str:
    if method == "xgboost":
        return "XGBoost model"
    return baselines.BASELINE_LABELS.get(method, method.replace("_", " ").title())
