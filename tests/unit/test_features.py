"""Unit tests for leakage-safe features and recursive inference."""

from __future__ import annotations

from datetime import date

import numpy as np

from ml.features import FEATURE_NAMES, build_matrix, feature_row, split_dates
from ml.predict import recursive_forecast
from ml.preprocessing import to_daily_series


class TestFeatureRow:
    def test_lags_use_only_past_values(self):
        values = list(range(1, 31))  # 1..30
        row = feature_row(values, product_code=7, day=date(2026, 1, 31))
        assert row[FEATURE_NAMES.index("lag_1")] == 30
        assert row[FEATURE_NAMES.index("lag_7")] == 24
        assert row[FEATURE_NAMES.index("lag_14")] == 17
        assert row[FEATURE_NAMES.index("lag_28")] == 3

    def test_calendar_features(self):
        row = feature_row([0] * 28, product_code=1, day=date(2026, 1, 3))  # Saturday
        assert row[FEATURE_NAMES.index("day_of_week")] == 5
        assert row[FEATURE_NAMES.index("is_weekend")] == 1.0

    def test_short_history_is_left_padded(self):
        row = feature_row([5, 6, 7], product_code=1, day=date(2026, 1, 1))
        assert len(row) == len(FEATURE_NAMES)
        assert row[FEATURE_NAMES.index("lag_1")] == 7


class TestBuildMatrix:
    def test_matrix_shape_and_split(self):
        series = to_daily_series([(f"2026-01-{d:02d}", float(d)) for d in range(1, 32)])
        matrix = build_matrix({1: series}, date_before="2026-02-01")
        assert matrix.X.shape[1] == len(FEATURE_NAMES)
        assert all(d < "2026-02-01" for d in matrix.dates)
        assert int(matrix.y[0]) == 29  # first target after the 28-day warm-up

    def test_split_dates_holdout(self):
        series = to_daily_series([(f"2026-03-{d:02d}", 1.0) for d in range(1, 21)])
        test_start, test_dates = split_dates({1: series}, horizon=7)
        assert test_start == "2026-03-14"
        assert test_dates[-1] == "2026-03-20"


class TestRecursiveForecast:
    def test_persistence_is_flat(self):
        history = [3, 4, 5, 6, 7, 8, 9, 10]
        # predict_one returns lag_1 (persistence)
        out = recursive_forecast(lambda X: X[:, FEATURE_NAMES.index("lag_1")],
                                 history, 1, date(2026, 1, 9), horizon=4)
        assert out == [10.0, 10.0, 10.0, 10.0]

    def test_outputs_are_clamped_non_negative(self):
        out = recursive_forecast(lambda X: np.array([-5.0]), [1.0] * 30, 1, date(2026, 1, 1), 3)
        assert out == [0.0, 0.0, 0.0]
