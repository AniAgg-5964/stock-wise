"""Layout arithmetic tests.

The content cap and the grid decisions are pure functions of a measured width, so
they are worth pinning down: the previous version expressed them as Flet
``ResponsiveRow`` breakpoint tables, whose reference width the Flet docs never
define, and the four-across KPI row silently stopped engaging on ordinary laptop
windows because of it. These tests encode the measured behaviour instead.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T
from ui.components.layout import (
    FILTER_WIDE_WIDTH,
    PANEL_TWO_UP_WIDTH,
    content_width,
    flow_row,
    panel_grid,
)


def _chrome(viewport: int, sidebar: int = T.SIDEBAR_WIDTH) -> int:
    """What is left of a window once the sidebar and padding are removed."""
    return viewport - sidebar - 2 * T.CONTENT_PADDING


class TestContentWidth:
    def test_unknown_viewport_fills_rather_than_guessing(self):
        """``None`` means 'not measured yet'. A width of ``None`` inside the row
        that applies the cap would hand the content unbounded width, so the
        helper has to return ``None`` and let the caller expand instead."""
        assert content_width(None, sidebar_width=T.SIDEBAR_WIDTH) is None
        assert content_width(0, sidebar_width=T.SIDEBAR_WIDTH) is None

    def test_a_window_too_narrow_to_cap_is_left_alone(self):
        # 600px window, expanded sidebar: 600 - 248 - 56 = 296, which is narrower
        # than a usable column, so capping would achieve nothing.
        assert content_width(600, sidebar_width=T.SIDEBAR_WIDTH) is None

    def test_below_the_cap_the_content_uses_everything_it_can(self):
        assert content_width(1366, sidebar_width=T.SIDEBAR_WIDTH) == _chrome(1366)
        assert content_width(1600, sidebar_width=T.SIDEBAR_WIDTH) == _chrome(1600)

    def test_a_wide_monitor_stops_stretching(self):
        """The reason MAX_CONTENT_WIDTH exists: on a 1920 monitor every card would
        otherwise become a wide empty band."""
        assert content_width(1920, sidebar_width=T.SIDEBAR_WIDTH) == T.MAX_CONTENT_WIDTH
        assert content_width(3840, sidebar_width=T.SIDEBAR_WIDTH) == T.MAX_CONTENT_WIDTH

    def test_never_wider_than_the_space_available(self):
        for viewport in range(400, 4001, 37):
            for sidebar in (T.SIDEBAR_WIDTH, T.SIDEBAR_WIDTH_COLLAPSED):
                width = content_width(viewport, sidebar_width=sidebar)
                assert width is None or width <= max(0, viewport - sidebar)

    def test_collapsing_the_sidebar_gives_the_content_more_room(self):
        expanded = content_width(1400, sidebar_width=T.SIDEBAR_WIDTH)
        collapsed = content_width(1400, sidebar_width=T.SIDEBAR_WIDTH_COLLAPSED)
        assert collapsed > expanded


class TestPanelGrid:
    @staticmethod
    def _spans(grid: ft.ResponsiveRow) -> list[int]:
        return [c.col for c in grid.controls]

    def test_panels_sit_side_by_side_when_there_is_room(self):
        grid = panel_grid([("a", 7), ("b", 5)], available_width=PANEL_TWO_UP_WIDTH)
        assert self._spans(grid) == [7, 5]

    def test_panels_stack_when_there_is_not(self):
        grid = panel_grid([("a", 7), ("b", 5)], available_width=PANEL_TWO_UP_WIDTH - 1)
        assert self._spans(grid) == [12, 12]

    def test_a_full_width_panel_stays_full_width_either_way(self):
        for width in (PANEL_TWO_UP_WIDTH - 1, PANEL_TWO_UP_WIDTH + 400):
            grid = panel_grid([("wide", 12)], available_width=width)
            assert self._spans(grid) == [12]

    def test_an_unmeasured_width_does_not_stack(self):
        """Same first-paint reasoning as the KPI strip."""
        stacked = panel_grid([("a", 7), ("b", 5)], available_width=PANEL_TWO_UP_WIDTH - 1)
        unknown = panel_grid([("a", 7), ("b", 5)], available_width=None)
        assert self._spans(unknown) != self._spans(stacked)


class TestFlowRow:
    @staticmethod
    def _spans(row: ft.ResponsiveRow) -> list[int]:
        return [c.col for c in row.controls]

    def test_three_across_on_a_wide_desktop(self):
        row = flow_row(["a", "b", "c"], available_width=FILTER_WIDE_WIDTH)
        assert self._spans(row) == [3, 3, 3]

    def test_two_across_when_narrower(self):
        row = flow_row(["a", "b", "c"], available_width=FILTER_WIDE_WIDTH - 1)
        assert self._spans(row) == [6, 6, 6]

    def test_an_explicit_span_survives_both_widths(self):
        """Forecasting hands a field its own span (2 of 12 next to a wider
        dropdown). Narrowing must fall back to the pair's ``sm`` span, not to the
        default of 3."""
        items = [("field", {"xs": 12, "sm": 6, "lg": 2}), ("dropdown", {"xs": 12, "sm": 6, "lg": 4})]
        assert self._spans(flow_row(items, available_width=FILTER_WIDE_WIDTH)) == [2, 4]
        assert self._spans(flow_row(items, available_width=FILTER_WIDE_WIDTH - 1)) == [6, 6]