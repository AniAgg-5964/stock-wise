"""StockWise — forecasting service.

Orchestrates the ML pipeline: pull demand history from the repository, build a
clean daily series, produce a forecast (a trained model when available, otherwise
a transparent baseline), persist it, and expose backtest metrics.

Forecasting never mutates stock and never raises for missing data \u2014 it returns an
``insufficient_data`` result instead so the UI can be honest.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from app.config import Config
from application.dto import ForecastMetrics, ForecastPoint, ForecastResult
from domain.exceptions import NotFoundError, StockWiseError
from domain.service_level import parse_service_level, z_for_service_level
from ml import baseline as baselines
from ml import evaluate as eval_metrics
from ml import intervals
from ml.features import FEATURE_SCHEMA_VERSION
from ml.preprocessing import (
    DayPoint,
    impute_censored,
    observed_count,
    quantities,
    recent_average,
    to_daily_series,
)


class ForecastService:
    def __init__(self, db, forecast_repo, product_repo, settings_repo=None, model_service=None) -> None:
        self.db = db
        self.forecasts = forecast_repo
        self.products = product_repo
        self.settings = settings_repo
        self.model_service = model_service
        # Memoised demand-history reads. These are pure functions of the
        # `daily_demand` table, so caching them is safe *provided* the cache is
        # dropped when a sale changes that table. See `invalidate_demand_cache`.
        self._series_cache: dict[tuple[int, str, bool], list[DayPoint]] = {}
        self._backtest_cache: dict[tuple[int, int, str], list[ForecastMetrics]] = {}

    def invalidate_demand_cache(self, product_id: int | None = None) -> None:
        """Forget memoised demand reads because the history has changed.

        Recording a sale appends to ``daily_demand``; every forecast, alert and
        reorder figure that depends on it must reflect that immediately. Called by
        the sales service with the affected products, or with no argument after a
        bulk import or seed run.

        Stored forecasts are deliberately **not** cached, so a regenerated forecast
        is always visible without invalidation.
        """
        if product_id is None:
            self._series_cache.clear()
            self._backtest_cache.clear()
            return
        for key in [k for k in self._series_cache if k[0] == product_id]:
            del self._series_cache[key]
        for key in [k for k in self._backtest_cache if k[0] == product_id]:
            del self._backtest_cache[key]

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

    def _baseline_setting(self) -> str:
        """The configured baseline choice: ``"best"`` or a specific method."""
        if self.settings is not None:
            value = self.settings.get("forecast_baseline_method")
            if value == "best" or value in baselines.BASELINE_METHODS:
                return value
        return Config.DEFAULT_BASELINE_METHOD

    def _resolve_baseline(
        self, product_id: int, horizon: int, requested: str | None = None
    ) -> tuple[str, str]:
        """Return ``(method, note)`` for the baseline fallback path.

        ``"best"`` (the default) uses the most accurate baseline for *this* product
        on the chronological holdout, so a product that suits a moving average is
        not forced onto seasonal naive. A named method pins one baseline instead.
        """
        if requested and requested != "best":
            return requested, ""
        setting = requested or self._baseline_setting()
        if setting == "best":
            metrics = [m for m in self.backtest(product_id, horizon=horizon) if m.wape is not None]
            if metrics:
                best = min(metrics, key=lambda m: m.wape)
                return best.method, (
                    f"Chose this product's most accurate baseline on holdout "
                    f"({best.label}, WAPE {best.wape:.0%})."
                )
            return "seasonal_naive", ""
        return setting, ""

    def _service_level(self) -> float:
        """Target service level for prediction intervals and statistical safety stock."""
        value = self.settings.get("service_level") if self.settings is not None else None
        return parse_service_level(value, Config.DEFAULT_SERVICE_LEVEL)

    def _z(self) -> float:
        return z_for_service_level(self._service_level())

    # -------------------------------------------------------------------- reads
    def demand_series(
        self, product_id: int, *, end: str | None = None, impute: bool = False
    ) -> list[DayPoint]:
        """The product's demand as a contiguous daily grid (oldest\u2192newest).

        ``impute=True`` replaces censored (out-of-stock) days with an estimate of
        true demand \u2014 used by the ML pipeline so a stockout is not learned as a
        real drop in demand. The default returns the raw observed series.

        Memoised, because rebuilding the grid meant re-reading the whole demand
        history and one dashboard render used to ask for this ~160 times. The
        result is a pure function of ``daily_demand``, so it is cleared by
        :meth:`invalidate_demand_cache` whenever a sale is recorded.
        """
        end = end or date.today().isoformat()
        cache_key = (int(product_id), end, bool(impute))
        cached = self._series_cache.get(cache_key)
        if cached is not None:
            return cached

        history = self.forecasts.get_demand_history_full(product_id)
        points = [(row[0], row[1]) for row in history]
        stockouts = {row[0] for row in history if row[2]}
        series = to_daily_series(points, end=end, stockout_dates=stockouts)
        result = impute_censored(series) if impute else series
        self._series_cache[cache_key] = result
        return result

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
                # Train/predict on censored-corrected demand so stockouts are not
                # mistaken for real demand drops.
                model_series = self.demand_series(product_id, end=today.isoformat(), impute=True)
                model_prediction = self.model_service.predict(
                    product, model_series, horizon, allow_candidate=(method == "xgboost")
                )
            if model_prediction is not None:
                chosen = "xgboost"
                predicted = model_prediction
            else:
                chosen, baseline_note = self._resolve_baseline(
                    product_id, horizon, None if method in ("auto", "xgboost") else method
                )
                predicted = baselines.forecast(chosen, values, horizon)
                if method == "xgboost":
                    note = "No trained model available \u2014 showing the baseline forecast instead."
                elif baseline_note:
                    note = baseline_note

        residual_std = self._residual_std(product_id, horizon, chosen)
        interval_level = None
        bounds: list[tuple[float, float] | None] = []
        if residual_std > 0:
            interval_level = self._service_level()
            lowers, uppers = intervals.interval_bounds(predicted, residual_std, z=self._z())
            bounds = list(zip(lowers, uppers))
        else:
            bounds = [None] * len(predicted)

        points = []
        for i, qty in enumerate(predicted):
            bound = bounds[i]
            points.append(
                ForecastPoint(
                    target_date=(today + timedelta(days=i + 1)).isoformat(),
                    predicted_qty=round(float(qty), 3),
                    lower_bound=None if bound is None else round(bound[0], 3),
                    upper_bound=None if bound is None else round(bound[1], 3),
                )
            )

        is_baseline = chosen != "xgboost"
        version = f"baseline:{chosen}" if is_baseline else f"xgboost:{FEATURE_SCHEMA_VERSION}"
        self.forecasts.replace_forecasts(
            product_id,
            [
                {
                    "target_date": p.target_date,
                    "predicted_qty": p.predicted_qty,
                    "lower_bound": p.lower_bound,
                    "upper_bound": p.upper_bound,
                }
                for p in points
            ],
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
            interval_level=interval_level,
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
        """Read the most recently stored forecast (no recomputation).

        The stored rows are re-read on every call, so a regenerated forecast shows
        up immediately. Everything derived from demand history comes from the
        memoised series, so this is cheap enough to call in a loop.
        """
        return self.latest_for_products([product_id]).get(int(product_id))

    def latest_for_products(self, product_ids: Iterable[int]) -> dict[int, ForecastResult]:
        """Stored forecasts for many products in one pass.

        A dashboard needs this for every product at once; doing it one at a time
        re-ran the same history rebuild dozens of times per render.
        """
        ids = sorted({int(product_id) for product_id in product_ids})
        if not ids:
            return {}
        rows_by_product = self.forecasts.get_forecasts_for_products(ids)
        results: dict[int, ForecastResult] = {}
        for product_id in ids:
            rows = rows_by_product.get(product_id)
            if not rows:
                continue
            results[product_id] = self._result_from_rows(product_id, rows)
        return results

    def _result_from_rows(self, product_id: int, rows: list[dict]) -> ForecastResult:
        product = self.products.get_by_id(product_id)
        version = rows[0].get("model_version") or "baseline:seasonal_naive"
        method, _, _ = _split_version(version)
        horizon = int(rows[0].get("horizon") or len(rows))
        residual_std = self._residual_std(product_id, horizon, method)
        has_bounds = any(r.get("lower_bound") is not None for r in rows)
        # One history read, reused for both figures below. Previously this rebuilt
        # the whole series twice per call on top of the backtest.
        series = self.demand_series(product_id)
        return ForecastResult(
            product_id=product_id,
            product_name=product.name if product else f"Product #{product_id}",
            horizon=horizon,
            method=method,
            method_label=_method_label(method),
            generated_at=rows[0].get("generated_at"),
            is_baseline=bool(rows[0].get("fallback_used")),
            fallback_used=bool(rows[0].get("fallback_used")),
            average_daily_demand=round(recent_average(series), 3),
            observed_days=observed_count(series),
            residual_std=round(residual_std, 3),
            interval_level=self._service_level() if has_bounds else None,
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
        """Chronological holdout evaluation of each baseline (PRD 7.6).

        Memoised: the holdout is a deterministic function of the demand series and
        the horizon, and this runs inside :meth:`latest` for every product.
        """
        horizon = horizon or self._horizon()
        # The series is built as of "today", so the date belongs in the key or the
        # cache would survive midnight with yesterday's history.
        cache_key = (int(product_id), int(horizon), date.today().isoformat())
        cached = self._backtest_cache.get(cache_key)
        if cached is not None:
            return cached

        series = self.demand_series(product_id, impute=True)
        if len(series) < horizon + Config.MIN_TRAINING_DAYS:
            self._backtest_cache[cache_key] = []
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
        self._backtest_cache[cache_key] = results
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
            product.id: self.demand_series(product.id, impute=True)
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
        """Holdout RMSE used as the sigma proxy for intervals / statistical safety stock."""
        for metric in self.backtest(product_id, horizon=horizon):
            if metric.method == method:
                return metric.rmse
        if method == "xgboost":
            # The model's holdout RMSE across all products is its error proxy.
            rmse = (self.model_status().get("metrics") or {}).get("rmse")
            if isinstance(rmse, (int, float)) and rmse > 0:
                return float(rmse)
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
