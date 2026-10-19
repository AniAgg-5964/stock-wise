"""Tests for the compact information graphics.

These render numbers a view has already loaded, so the properties worth pinning
are the ones a shopkeeper would misread if they broke: a meter that overflows its
cell, a downsampled sparkline that flattens the very spike it was added to show,
and a control tree that is not safe inside a ``DataCell``.

The ``DataCell`` part is not hypothetical. Flet 1.0 lays cell content out with
unbounded width, and a stretchy ``Row`` or bare ``Column`` inside a cell renders
the **entire** table blank. That has already cost this app one blank screen, so
it is asserted rather than assumed.
"""

from __future__ import annotations

import flet as ft

from ui.components.sparkline import _downsample, meter, mini_bars


def _walk(control: ft.Control, depth: int = 0):
    yield control
    if depth > 40:  # pragma: no cover - defensive
        return
    for attr in ("controls", "content"):
        children = getattr(control, attr, None)
        if isinstance(children, (list, tuple)):
            for child in children:
                if isinstance(child, ft.Control):
                    yield from _walk(child, depth + 1)
        elif isinstance(children, ft.Control):
            yield from _walk(children, depth + 1)


def _bars(control: ft.Control) -> list[ft.Control]:
    """The micro-bars inside a sparkline."""
    rows = [n for n in _walk(control) if isinstance(n, ft.Row)]
    return list(rows[0].controls) if rows else []


class TestMeter:
    def test_a_full_meter_fills_its_track(self):
        fill = next(c for c in _walk(meter(50, 50, color="#fff")) if c.width == 64)
        assert fill.width == 64

    def test_the_fill_never_overflows_the_cell(self):
        """A snapshot with more usable stock than its reorder point is normal, not
        an error. The bar has to clamp or it pushes the table sideways."""
        for value, maximum in ((1000, 10), (-5, 10), (10, 0), (5, 0)):
            widths = [c.width for c in _walk(meter(value, maximum, color="#fff"))
                      if isinstance(c.width, int)]
            assert max(widths) <= 64, f"{value}/{maximum} overflowed the track"

    def test_zero_still_shows_a_stub(self):
        """Empty and absent should not look identical."""
        widths = [c.width for c in _walk(meter(0, 10, color="#fff")) if isinstance(c.width, int)]
        assert min(widths) >= 6, "an empty meter rendered nothing at all"

    def test_it_is_not_a_surface(self):
        """The enclosing card already has the edge. A meter that drew its own
        border would put two edges on one row."""
        m = meter(5, 10, color="#fff")
        assert m.border is None
        assert m.border_radius is not None  # the track is rounded, which is not an edge


class TestMiniBars:
    def test_a_long_series_is_capped(self):
        rendered = _bars(mini_bars([float(v) for v in range(200)]))
        assert 0 < len(rendered) <= 12, f"{len(rendered)} bars rendered"

    def test_the_bars_fit_inside_the_declared_width(self):
        """Explicit widths, not flex: that is what makes this safe in a cell."""
        spark = mini_bars([1.0, 4.0, 2.0, 6.0], width=58, height=16)
        bars = _bars(spark)
        total = sum(b.width for b in bars) + 2 * (len(bars) - 1)
        assert total <= 58, f"bars totalled {total}px inside a 58px sparkline"

    def test_downsampling_keeps_the_spike(self):
        """Averaging buckets would flatten exactly what the sparkline was added
        to reveal: a single big day."""
        values = [1.0] * 90 + [40.0] + [1.0] * 9
        reduced = _downsample(values, 12)
        assert max(reduced) == 40.0, "the peak was averaged away"

    def test_a_short_series_is_untouched(self):
        assert _downsample([1.0, 2.0, 3.0], 12) == [1.0, 2.0, 3.0]

    def test_an_empty_or_flat_series_renders_without_error(self):
        for values in ([], [0.0, 0.0, 0.0]):
            control = mini_bars(values)
            assert isinstance(control, ft.Control)
            assert control.width is not None, "must stay a fixed size for table cells"

    def test_the_tallest_bar_reaches_the_top(self):
        bars = _bars(mini_bars([0.0, 0.0, 9.0], height=20))
        assert max(b.height for b in bars) == 18  # height 20 less the 2px floor

    def test_every_bar_has_a_visible_height(self):
        """A zero-demand day still gets a stub, so the week reads as seven days.
        This is the all-zero-peak case that used to divide by zero."""
        bars = _bars(mini_bars([0.0] * 7))
        assert len(bars) == 7
        assert all(b.height >= 2 for b in bars)


class TestCellSafety:
    """Flet 1.0 renders a whole DataTable blank when a cell holds a stretchy Row
    or a bare Column. Both graphics are placed inside cells, so neither is allowed
    to contain anything that flexes.

    The check is on *truthy* ``expand``, not on ``expand is not False``: Flet
    1.0.4 leaves the attribute as ``None`` when it is not set, and the shipped
    ``table.entity_cell`` relies on exactly that plus ``tight=True``. Demanding
    an explicit ``False`` would have failed code that demonstrably renders.
    """

    @staticmethod
    def _assert_cell_safe(control: ft.Control) -> None:
        for node in _walk(control):
            if isinstance(node, (ft.Row, ft.Column, ft.Container)) and getattr(node, "expand", None):
                raise AssertionError(
                    f"{type(node).__name__} has expand={node.expand!r}; a stretchy control "
                    "inside a DataCell blanks the whole table in Flet 1.0"
                )

    def test_meter_is_safe_inside_a_cell(self):
        self._assert_cell_safe(meter(5, 10, color="#fff"))

    def test_sparkline_is_safe_inside_a_cell(self):
        self._assert_cell_safe(mini_bars([1.0, 5.0, 2.0]))