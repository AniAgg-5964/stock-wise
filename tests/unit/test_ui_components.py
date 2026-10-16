"""Component-level UI tests for the restyled widgets.

Covers the KPI card sizing rule that keeps long money values (``₹1,23,456.00``)
on a single line inside a narrow card instead of wrapping onto a second line.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T
from domain.money import format_money
from ui.components.kpi_card import _value_size, kpi_card


def _texts(control: ft.Control):
    def walk(node, depth=0):
        yield node
        if depth > 20:  # pragma: no cover - defensive
            return
        for attr in ("controls", "content"):
            children = getattr(node, attr, None)
            if isinstance(children, (list, tuple)):
                for child in children:
                    if isinstance(child, ft.Control):
                        yield from walk(child, depth + 1)
            elif isinstance(children, ft.Control):
                yield from walk(children, depth + 1)

    return [n for n in walk(control) if isinstance(n, ft.Text)]


def test_value_size_shrinks_for_longer_strings():
    sizes = [_value_size(s) for s in ("15", "₹29,209.00", "₹1,23,456.00", "₹1,23,45,678.90")]
    assert sizes == sorted(sizes, reverse=True)
    assert sizes[0] == T.FONT_DISPLAY
    assert all(size <= T.FONT_DISPLAY for size in sizes)


def test_short_values_keep_the_display_size():
    assert _value_size("15") == T.FONT_DISPLAY
    assert _value_size(format_money(29209)) == T.FONT_DISPLAY


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
