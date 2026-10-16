"""Unit tests for the pure forecasting math (baselines, metrics, preprocessing)."""

from __future__ import annotations

import math

from ml import baseline, evaluate
from ml.preprocessing import impute_censored, observed_count, quantities, to_daily_series


class TestBaselines:
    def test_seasonal_naive_repeats_weekday_pattern(self):
        history = [10, 11, 12, 13, 14, 15, 16, 20, 21, 22]
        out = baseline.seasonal_naive(history, horizon=7)
        assert out == [13, 14, 15, 16, 20, 21, 22]

    def test_seasonal_naive_recurses_beyond_history(self):
        history = list(range(1, 15))  # 14 days
        out = baseline.seasonal_naive(history, horizon=9)
        # first 7 reuse history tail; day 8 repeats day 1's forecast, day 9 repeats day 2's
        assert out[:7] == [8, 9, 10, 11, 12, 13, 14]
        assert out[7] == out[0]
        assert out[8] == out[1]

    def test_seasonal_naive_handles_empty_history(self):
        assert baseline.seasonal_naive([], horizon=3) == [0.0, 0.0, 0.0]

    def test_moving_average_is_flat(self):
        out = baseline.moving_average([2, 4, 6, 8], horizon=3, window=2)
        assert out == [7.0, 7.0, 7.0]

    def test_mean_forecast(self):
        assert baseline.mean_forecast([5, 10, 15], horizon=2) == [10.0, 10.0]

    def test_outputs_are_non_negative(self):
        assert baseline.moving_average([-5], horizon=2) == [0.0, 0.0]


class TestMetrics:
    def test_mae_rmse(self):
        actual = [10, 20, 30]
        pred = [12, 18, 33]
        assert evaluate.mae(actual, pred) == 7 / 3
        assert round(evaluate.rmse(actual, pred), 4) == round(math.sqrt((4 + 4 + 9) / 3), 4)

    def test_bias_sign(self):
        assert evaluate.bias([10, 10], [12, 12]) == 2.0
        assert evaluate.bias([10, 10], [8, 8]) == -2.0

    def test_wape(self):
        assert evaluate.wape([10, 10], [12, 8]) == 20.0

    def test_wape_is_none_when_no_demand(self):
        assert evaluate.wape([0, 0], [1, 2]) is None
        assert evaluate.format_wape(None) == "n/a (zero demand)"

    def test_metrics_bundle(self):
        m = evaluate.metrics([1, 2, 3], [1, 2, 3])
        assert m["mae"] == 0.0 and m["n"] == 3


class TestPreprocessing:
    def test_daily_series_fills_gaps_as_unobserved(self):
        series = to_daily_series([("2026-01-01", 5), ("2026-01-03", 7)], end="2026-01-04")
        assert [p.date for p in series] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
        assert quantities(series) == [5.0, 0.0, 7.0, 0.0]
        assert observed_count(series) == 2
        assert series[1].observed is False

    def test_daily_series_extends_to_end_without_history(self):
        series = to_daily_series([], end="2026-02-01")
        assert len(series) == 1 and series[0].quantity == 0.0

    def test_stockout_days_are_flagged(self):
        series = to_daily_series(
            [("2026-01-01", 5), ("2026-01-02", 1), ("2026-01-03", 7)],
            stockout_dates={"2026-01-02"},
        )
        assert [p.stockout for p in series] == [False, True, False]

    def test_impute_censored_uses_same_weekday_mean(self):
        # 2026-01-01 and 2026-01-08 are both a Thursday; the second is censored.
        series = to_daily_series(
            [("2026-01-01", 10.0), ("2026-01-08", 1.0)],
            stockout_dates={"2026-01-08"},
        )
        imputed = {p.date: p for p in impute_censored(series)}

        assert imputed["2026-01-08"].quantity == 10.0  # raised to the Thursday mean
        assert imputed["2026-01-08"].stockout is True
        assert imputed["2026-01-08"].imputed is True
        assert imputed["2026-01-01"].imputed is False

    def test_impute_censored_never_lowers_recorded_sales(self):
        series = to_daily_series(
            [("2026-01-01", 10.0), ("2026-01-08", 50.0)],
            stockout_dates={"2026-01-08"},
        )
        imputed = {p.date: p for p in impute_censored(series)}
        assert imputed["2026-01-08"].quantity == 50.0

    def test_impute_censored_is_a_noop_without_stockouts(self):
        series = to_daily_series([("2026-01-01", 5.0)])
        assert impute_censored(series) == list(series)
