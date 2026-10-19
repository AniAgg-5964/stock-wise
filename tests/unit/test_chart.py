"""Tests for the dependency-free chart geometry.

``area_chart`` is assembled from plain Flet containers, so the only thing that
determines whether the line looks smooth or broken is the arithmetic behind the
slices. These tests pin that arithmetic directly.

The original defect: linear interpolation with four samples per segment plus a
border on the top of every slice, which rendered a notched staircase. A jumpy
series is used on purpose - smooth rendering of a gentle series proves nothing.
"""

from __future__ import annotations

import flet as ft

from ui.components.chart import (
    _MAX_SLICES,
    _curve_pixels,
    _interpolate,
    _sample_steps,
    area_chart,
    bar_chart,
    nice_axis_max,
)

# Deliberately spiky: flat ramps would hide a stepped curve.
SPIKY = [5.0, 40.0, 6.0, 35.0, 5.0, 45.0, 4.0]

PLOT_HEIGHT = 200


def _walk(control: ft.Control, depth: int = 0):
    yield control
    if depth > 60:  # pragma: no cover - defensive
        return
    for attr in ("controls", "content"):
        children = getattr(control, attr, None)
        if isinstance(children, (list, tuple)):
            for child in children:
                if isinstance(child, ft.Control):
                    yield from _walk(child, depth + 1)
        elif isinstance(children, ft.Control):
            yield from _walk(children, depth + 1)


def test_the_line_is_a_ribbon_not_a_per_slice_border():
    """The other half of the "broken" chart: a border on the top of every slice
    put a visible notch at every column boundary. The line is now one
    constant-thickness ribbon laid over the fill, so nothing in the plot should
    carry a border at all."""
    chart = area_chart([1.0, 5.0, 2.0, 6.0, 3.0], labels=["a", "b", "c", "d", "e"])
    bordered = [
        c for c in _walk(chart)
        if isinstance(c, ft.Container) and c.border and getattr(c.border, "top", None)
    ]
    assert not bordered, f"{len(bordered)} containers still draw a border inside the chart"


def test_both_charts_build_with_a_forecast_split():
    for build in (area_chart, bar_chart):
        control = build([1.0, 4.0, 2.0, 5.0], ["a", "b", "c", "d"], forecast_from=2)
        assert isinstance(control, ft.Control)


def test_empty_series_shows_a_message_not_a_broken_chart():
    for build in (area_chart, bar_chart):
        control = build([], [])
        assert any(isinstance(n, ft.Text) for n in _walk(control))


def _pixels(values, *, plot_height=PLOT_HEIGHT):
    steps = _sample_steps(len(values))
    smooth = _interpolate(values, steps)
    peak = max(smooth) * 1.15 if smooth else 1.0
    return _curve_pixels(smooth, plot_height, peak)


def test_adjacent_columns_differ_by_at_most_a_few_pixels():
    """The property that makes the curve read as a line rather than a staircase.

    On a chart ~600px wide with ~220 columns each column is under 3px, so a
    double-digit change across it is a steep slope - continuous, not a step. The
    removed per-slice border, which put a notch at every single column, was the
    other half of the "broken" look and is pinned separately below.
    """
    pixels = _pixels(SPIKY)
    jumps = [abs(b - a) for a, b in zip(pixels, pixels[1:])]
    assert max(jumps) <= PLOT_HEIGHT // 10, (
        f"largest step between adjacent columns was {max(jumps)}px, "
        f"more than a tenth of the {PLOT_HEIGHT}px plot"
    )


def test_the_curve_reaches_every_data_point():
    """Resampling must not flatten the peaks it passes through."""
    pixels = _pixels(SPIKY)
    peak = max(pixels)
    assert peak >= PLOT_HEIGHT * 0.8, "the tallest point should reach near the top"
    assert min(pixels) <= PLOT_HEIGHT * 0.15, "the shortest point should stay near the bottom"


def test_the_curve_starts_and_ends_on_the_real_values():
    values = SPIKY
    pixels = _pixels(values)
    first = max(pixels) * values[0] / max(values)
    last = max(pixels) * values[-1] / max(values)
    assert abs(pixels[0] - first) <= PLOT_HEIGHT * 0.05
    assert abs(pixels[-1] - last) <= PLOT_HEIGHT * 0.05


def test_a_flat_series_renders_flat_without_dividing_by_zero():
    """A level series must not collapse or raise: the chart reserves headroom, so
    the answer is a constant height below the plot top, not the plot height."""
    pixels = _pixels([3.0, 3.0, 3.0])
    assert len(set(pixels)) == 1, f"expected one flat height, got {set(pixels)}"
    assert pixels[0] < PLOT_HEIGHT, "a flat series should keep headroom below the top"


class TestNiceAxis:
    """The 81 / 61 / 41 / 20 / 0 defect.

    The axis used to be ``peak * 1.15`` with ticks at quarters of it, so the
    labels inherited whatever the headroom factor produced. A rounded axis keeps
    every gridline label a round number.
    """

    @staticmethod
    def _labels(peak: float, divisions: int = 4) -> list[float]:
        axis = nice_axis_max(peak)
        return [axis * (divisions - i) / divisions for i in range(divisions + 1)]

    def test_every_gridline_label_is_whole(self):
        for peak in (3, 7, 12, 41, 70, 93, 400, 1234, 29209, 1_200_000):
            for label in self._labels(peak):
                assert abs(label - round(label)) < 1e-6, (
                    f"peak {peak} produced a fractional label {label}"
                )

    def test_labels_are_round_rather_than_arbitrary(self):
        """The exact peak that produced 81 / 61 / 41 / 20 / 0 on the dashboard."""
        labels = self._labels(70 * 1.15)
        assert all(abs(v - round(v)) < 1e-6 for v in labels)
        assert labels[0] > 70 * 1.15 - 1e-6, "the axis should still reserve headroom"

    def test_the_axis_never_cuts_off_the_peak(self):
        for peak in (3, 7, 12, 41, 70, 93, 400, 1234, 29209):
            assert nice_axis_max(peak) >= peak

    def test_a_flat_or_empty_series_still_has_an_axis(self):
        assert nice_axis_max(0) > 0
        assert nice_axis_max(-5) > 0


def test_the_tallest_bar_keeps_headroom():
    """Bars are measured against the rounded axis, not against the tallest bar, so
    a one-day series does not fill the plot from edge to edge."""
    chart = bar_chart([100.0], ["16"])
    bars = [
        c for c in _walk(chart)
        if isinstance(c, ft.Container) and isinstance(c.height, int) and c.height > 3
        and getattr(c, "border_radius", None) is not None
    ]
    assert bars, "expected at least one bar"
    assert bars[0].height < 190, "the only bar filled the whole plot height"


def test_a_single_point_is_a_bar_not_a_full_width_slab():
    """The demo data puts every sale on one date, so this is the series Reports
    actually renders. A stretched cell would span the entire chart."""
    chart = bar_chart([1234.0], ["16"])
    cells = list(chart.controls)
    assert len(cells) == 1
    assert cells[0].expand is not True, "a single bar must not expand to fill the row"
    assert cells[0].width is not None, "a single bar needs a fixed width"
    assert chart.alignment == ft.MainAxisAlignment.CENTER


def test_a_long_series_still_fills_the_width():
    """Fixing the short case must not leave a 30-day chart as a cluster in the
    middle of the panel."""
    chart = bar_chart([float(v) for v in range(1, 31)])
    assert all(c.expand is True for c in chart.controls)
    assert chart.alignment == ft.MainAxisAlignment.START


def test_slice_count_stays_bounded_for_long_series():
    """Each slice is ~3 Flutter controls, so the chart must not oversample a long
    series into thousands of nodes and undo the render time we won back."""
    for count in (7, 21, 90, 400, 2000):
        slices = len(_interpolate([1.0] * count, _sample_steps(count)))
        # One column per data point is the floor: a series cannot be drawn with
        # fewer columns than it has points.
        assert slices <= max(count, _MAX_SLICES + 1), (
            f"{count} points rendered as {slices} slices"
        )


def test_short_series_still_gets_smooth_sampling():
    assert _sample_steps(2) >= 2
    assert _sample_steps(21) >= 2


def test_interpolation_passes_through_every_data_point():
    steps = 8
    values = [1.0, 5.0, 2.0, 8.0]
    smooth = _interpolate(values, steps)
    # Every original value should appear somewhere in the sampled curve.
    for value in values:
        assert any(abs(s - value) < 0.05 for s in smooth), f"{value} was skipped"


def test_single_point_series_is_safe():
    assert _interpolate([7.0], 8) == [7.0]
    assert _interpolate([], 8) == []
