"""Component-level UI tests for the restyled widgets.

Covers the KPI card sizing rule that keeps long money values (``₹1,23,456.00``)
on a single line inside a narrow card instead of wrapping onto a second line.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T
from application.services.supplier_research_service import SourceCandidate
from domain.money import format_money
from ui.components.kpi_card import _value_size, kpi_card, value_fits
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
    assert sizes[0] == T.FONT_DISPLAY
    assert all(size <= T.FONT_DISPLAY for size in sizes)


def test_short_values_keep_the_display_size():
    assert _value_size("15") == T.FONT_DISPLAY
    assert _value_size(format_money(29209)) == T.FONT_DISPLAY


def test_realistic_money_values_fit_a_four_up_card():
    """The actual requirement behind the sizing ladder.

    The card is no_wrap, so a value that does not fit is clipped, not wrapped.
    This was checked against the old layout, where a 40px icon tile beside the
    number left only ~156px and made 32px impossible.
    """
    for amount in (0, 15, 999, 29209, 123456, 1234567, 12345678, 99999999):
        value = format_money(amount)
        assert value_fits(value), f"{value!r} needs more than the card width"


def test_even_an_oversized_value_does_not_grow_the_font():
    """Sanity: the ladder is monotonic, so a pathological string cannot ask for a
    *larger* font than a short one."""
    sizes = [_value_size(s) for s in ("1", "1234567890", "₹1,23,45,678.90", "x" * 40)]
    assert sizes == sorted(sizes, reverse=True)


def test_kpi_card_value_never_wraps():
    value = format_money(29209)
    card = kpi_card("Total Stock Value", value, subtitle="At cost", col={"xs": 12, "lg": 3})
    rendered = [t for t in _texts(card) if t.value == value]
    assert len(rendered) == 1
    assert rendered[0].no_wrap is True
    assert rendered[0].size == _value_size(value)


def test_kpi_card_without_col_expands():
    """Cards dropped into a plain Row fill it; grid cards are placed by ``col``."""
    assert kpi_card("A", "1").expand is True
    assert kpi_card("A", "1", col={"xs": 12, "lg": 3}).expand is False


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
