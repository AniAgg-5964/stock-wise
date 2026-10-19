"""Component-level UI tests for the restyled widgets.

Covers the KPI card sizing rule that keeps long money values (``₹1,23,456.00``)
on a single line inside a narrow card instead of wrapping onto a second line.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T
from application.services.supplier_research_service import SourceCandidate
from domain.money import format_money
from ui.components.kpi_card import (
    KPI_FOUR_UP_WIDTH,
    KpiMetric,
    _VALUE_BUDGET_PX,
    _span_for,
    _value_size,
    kpi_strip,
    value_fits,
)
from ui.components.layout import list_row
from ui.views.supplier_research_panel import _confidence_color, _site_cell


def _walk(control: ft.Control):
    """Every control in a tree, including the root."""
    def visit(node, depth=0):
        yield node
        if depth > 20:  # pragma: no cover - defensive
            return
        for attr in ("controls", "content"):
            children = getattr(node, attr, None)
            if isinstance(children, (list, tuple)):
                for child in children:
                    if isinstance(child, ft.Control):
                        yield from visit(child, depth + 1)
            elif isinstance(children, ft.Control):
                yield from visit(children, depth + 1)

    return list(visit(control))


def _texts(control: ft.Control):
    return [n for n in _walk(control) if isinstance(n, ft.Text)]


def test_value_size_shrinks_for_longer_strings():
    sizes = [_value_size(s) for s in ("15", "₹29,209.00", "₹1,23,456.00", "₹1,23,45,678.90")]
    assert sizes == sorted(sizes, reverse=True)
    assert sizes[0] == T.FONT_METRIC
    assert all(size <= T.FONT_METRIC for size in sizes)


def test_short_values_keep_the_display_size():
    assert _value_size("15") == T.FONT_METRIC
    assert _value_size(format_money(29209)) == T.FONT_METRIC


def test_realistic_money_values_fit_a_metric_cell():
    """The actual requirement behind the sizing ladder.

    A metric value is ``no_wrap``, so one that does not fit is clipped rather than
    wrapped. The budget is the text width of one cell in a four-up strip.
    """
    for amount in (0, 15, 999, 29209, 123456, 1234567, 12345678, 99999999):
        value = format_money(amount)
        assert value_fits(value), f"{value!r} needs more than the metric cell width"


def test_even_an_oversized_value_does_not_grow_the_font():
    """Sanity: the ladder is monotonic, so a pathological string cannot ask for a
    *larger* font than a short one."""
    sizes = [_value_size(s) for s in ("1", "1234567890", "₹1,23,45,678.90", "x" * 40)]
    assert sizes == sorted(sizes, reverse=True)


def test_four_metrics_stay_on_one_row_at_the_measured_width():
    """The bug this replaces.

    Four-across used to sit behind a ``ResponsiveRow`` breakpoint of 1240, which
    the Flet docs never define as a page *or* a container width. Measured against
    the container - a window minus the sidebar and the content padding - that
    threshold engaged at a ~1544px window, so a 1366 or 1440 laptop rendered two
    enormous half-empty tiles instead. The width is now measured, not guessed.
    """
    # Derived from the text budget, so the two cannot drift apart.
    assert KPI_FOUR_UP_WIDTH == 4 * (_VALUE_BUDGET_PX + 2 * 10 + 2 * 18) + 3 * 18

    # Four across must engage on an ordinary laptop window. With the sidebar and
    # content padding removed, 1366 and 1440 both clear the threshold.
    for window in (1366, 1440, 1600, 1920):
        content = window - T.SIDEBAR_WIDTH - 2 * T.CONTENT_PADDING
        assert content >= KPI_FOUR_UP_WIDTH, (
            f"{window}px window leaves {content}px of content, under the "
            f"{KPI_FOUR_UP_WIDTH}px needed for four across"
        )

    # ...and must not engage when there genuinely is not room, which is the 2x2.
    assert _span_for(4, width=KPI_FOUR_UP_WIDTH - 1) == 6
    assert _span_for(4, width=KPI_FOUR_UP_WIDTH) == 3


def test_an_unmeasured_viewport_does_not_look_narrow():
    """Before the first resize event the width is unknown, not zero. Treating it
    as zero would stack everything on the first paint and then jump."""
    assert _span_for(4, width=None) == _span_for(4, width=KPI_FOUR_UP_WIDTH + 400)


def test_kpi_strip_is_one_surface_not_four_cards():
    """The point of the strip: four metrics, one border, one radius, no shadow.

    One bordered, shadowed tile per metric is what made the dashboard read as a
    pile of boxes.
    """
    strip = kpi_strip([KpiMetric(f"M{i}", str(i)) for i in range(4)])
    surfaces = [c for c in _walk(strip) if isinstance(c, ft.Container) and c.border]
    shadowed = [c for c in _walk(strip) if isinstance(c, ft.Container) and c.shadow]
    assert len(surfaces) == 1, f"expected a single surface, found {len(surfaces)}"
    assert not shadowed, "a card must carry a border or a shadow, never both"


def test_metric_value_never_wraps():
    value = format_money(29209)
    strip = kpi_strip([KpiMetric("Total Stock Value", value, caption="At cost")])
    rendered = [t for t in _texts(strip) if t.value == value]
    assert len(rendered) == 1
    assert rendered[0].no_wrap is True
    assert rendered[0].size == _value_size(value)


def test_a_list_row_draws_no_box_of_its_own():
    """Rows were filled, rounded boxes stacked inside a card - six surfaces in one
    panel, none of them important."""
    row = list_row(title="Surf Excel 1kg is low", subtitle="Usable 9 · reorder point 10")
    assert row.border_radius is None
    assert row.bgcolor is None
    assert not row.shadow


def test_a_list_row_can_draw_a_divider_instead():
    row = list_row(title="Britannia Brown Bread is out of stock", divider=True)
    assert row.border is not None and row.border.bottom is not None


def test_research_site_cell_never_uses_a_stretchy_row():
    """A stretchy Row inside a DataCell silently blanks the whole DataTable.

    Flet lays cell content out with unbounded width, so any Row there must be
    tight. This guards the research candidate table specifically.
    """
    blocked = SourceCandidate(
        url="https://www.indiamart.com/p", site_name="indiamart.com", host="indiamart.com",
        block_reason="often blocks automated access",
    )

    cell = _site_cell(blocked)
    rows = [r for r in _walk(cell) if isinstance(r, ft.Row)]

    assert rows, "expected a Row holding the two-line site name"
    assert all(row.tight is True for row in rows), "a non-tight Row blanks the table"
    assert all(not isinstance(c, ft.Column) or c.tight is True
               for c in _walk(cell) if isinstance(c, ft.Column))


def test_research_site_cell_shows_the_block_warning():
    blocked = SourceCandidate(
        url="https://www.indiamart.com/p", site_name="indiamart.com", host="indiamart.com",
        block_reason="often blocks automated access",
    )

    texts = [t.value for t in _walk(_site_cell(blocked)) if isinstance(t, ft.Text)]

    assert "indiamart.com" in texts
    assert "often blocks automated access" in texts


def test_research_site_cell_mentions_an_already_saved_supplier():
    saved = SourceCandidate(
        url="https://example.com/atta", site_name="example.com", host="example.com",
        supplier_id=7,
    )

    texts = [t.value for t in _walk(_site_cell(saved)) if isinstance(t, ft.Text)]

    assert "Already saved as a supplier" in texts


def test_research_site_cell_stays_plain_when_there_is_nothing_to_say():
    clean = SourceCandidate(url="https://example.com/atta", site_name="example.com")

    assert [t.value for t in _walk(_site_cell(clean)) if isinstance(t, ft.Text)] == [
        "example.com"
    ]


def test_confidence_colour_reflects_how_clearly_the_page_stated_it():
    assert _confidence_color(0.95) == T.STATUS_HEALTHY
    assert _confidence_color(0.75) == T.STATUS_HEALTHY
    assert _confidence_color(0.6) == T.STATUS_WARNING
    assert _confidence_color(0.2) == T.TEXT_TERTIARY
