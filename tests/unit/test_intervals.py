"""Unit tests for prediction intervals and the service-level mapping."""

from __future__ import annotations

from domain.service_level import (
    SERVICE_LEVEL_Z,
    parse_service_level,
    supported_service_levels,
    z_for_service_level,
)
from ml.intervals import interval_bounds


class TestServiceLevel:
    def test_z_matches_table(self):
        assert z_for_service_level(0.90) == 1.28
        assert z_for_service_level(0.95) == 1.65

    def test_accepts_percent_and_percent_sign(self):
        assert z_for_service_level("90") == 1.28
        assert z_for_service_level("90%") == 1.28

    def test_unknown_value_snaps_to_nearest(self):
        assert z_for_service_level(0.91) in (SERVICE_LEVEL_Z[0.90], SERVICE_LEVEL_Z[0.92])

    def test_bad_value_falls_back(self):
        assert parse_service_level("not-a-number") == 0.90
        assert parse_service_level(None) == 0.90

    def test_levels_below_and_above_clamp(self):
        levels = supported_service_levels()
        assert z_for_service_level(0.1) == SERVICE_LEVEL_Z[levels[0]]
        assert z_for_service_level(0.999) == SERVICE_LEVEL_Z[levels[-1]]


class TestIntervals:
    def test_widths_grow_with_horizon(self):
        lowers, uppers = interval_bounds([10.0, 10.0, 10.0, 10.0], residual_std=2.0, z=1.28)
        widths = [u - l for l, u in zip(lowers, uppers)]
        assert widths[0] < widths[1] < widths[2] < widths[3]
        assert round(widths[0], 6) == round(2 * 1.28 * 2.0, 6)

    def test_lower_bound_never_negative(self):
        lowers, uppers = interval_bounds([1.0], residual_std=5.0)
        assert lowers[0] == 0.0
        assert uppers[0] == 1.0 + 1.28 * 5.0

    def test_zero_sigma_is_a_point(self):
        lowers, uppers = interval_bounds([3.0, 4.0], residual_std=0.0)
        assert lowers == [3.0, 4.0] and uppers == [3.0, 4.0]
