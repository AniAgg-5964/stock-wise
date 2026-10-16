"""Shell smoke tests: the sidebar and every routed view build without a live page.

These validate Flet API usage (control construction) without launching a window.
The ``wired_app_context`` fixture points the shared context at a temp database.
"""

from __future__ import annotations

import flet as ft
import pytest

from app.navigation import NAV_ITEMS, build_sidebar
from domain.entities import Product
from domain.enums import MovementType
from ui.views.registry import VIEW_META, build_view


class _StubPage:
    """Minimal stand-in for ft.Page during view construction."""

    def __init__(self) -> None:
        self.controls: list = []

    def add(self, *controls) -> None:  # pragma: no cover - not used during build
        self.controls.append(controls)

    def update(self) -> None:  # pragma: no cover - not used during build
        pass

    def show_dialog(self, dialog) -> None:  # pragma: no cover - not used during build
        pass

    def pop_dialog(self) -> None:  # pragma: no cover - not used during build
        pass


def test_every_nav_route_has_view_meta():
    for route, _label, _icon in NAV_ITEMS:
        assert route in VIEW_META, f"Missing view meta for {route}"


def test_sidebar_builds():
    page = _StubPage()
    sidebar = build_sidebar(page, "/", lambda route: None)
    assert isinstance(sidebar, ft.Control)


def test_every_route_builds_a_view(wired_app_context):
    page = _StubPage()
    for route, _label, _icon in NAV_ITEMS:
        view = build_view(route, page, lambda r: None)
        assert isinstance(view, ft.Control)


def test_product_detail_route_builds_with_data(wired_app_context):
    page = _StubPage()
    product = wired_app_context.product_service.create_product(
        Product(sku="SKU-1", name="Test Product")
    )
    wired_app_context.inventory_service.receive_stock(
        product.id, 5, movement_type=MovementType.OPENING_STOCK
    )
    view = build_view(f"/product/{product.id}", page, lambda r: None)
    assert isinstance(view, ft.Control)


def test_product_detail_route_handles_missing_product(wired_app_context):
    page = _StubPage()
    view = build_view("/product/999999", page, lambda r: None)
    assert isinstance(view, ft.Control)


# --------------------------------------------------------------------------- layout guards
# These lock in the Flet 1.0.4 workarounds documented in AGENTS.md so the UI cannot
# silently regress into a blank grey page or an invisible DataTable.

def _walk(control: ft.Control, depth: int = 0):
    yield control
    if depth > 60:  # pragma: no cover - defensive
        return
    for attr in ("controls", "content", "actions", "cells"):
        children = getattr(control, attr, None)
        if isinstance(children, (list, tuple)):
            for child in children:
                if isinstance(child, ft.Control):
                    yield from _walk(child, depth + 1)
        elif isinstance(children, ft.Control):
            yield from _walk(children, depth + 1)


def test_no_view_uses_row_wrap(wired_app_context):
    """``ft.Row(wrap=True)`` renders the whole page as a blank grey block in Flet 1.0."""
    page = _StubPage()
    for route, _label, _icon in NAV_ITEMS:
        view = build_view(route, page, lambda r: None)
        offenders = [n for n in _walk(view) if isinstance(n, ft.Row) and getattr(n, "wrap", False)]
        assert not offenders, f"{route} uses ft.Row(wrap=True)"


def test_no_data_cell_uses_unbounded_layout(wired_app_context):
    """A stretchy Row / bare Column inside ``ft.DataCell`` blanks the whole table."""
    page = _StubPage()
    for route, _label, _icon in NAV_ITEMS:
        view = build_view(route, page, lambda r: None)
        offenders = [
            n for n in _walk(view)
            if isinstance(n, ft.DataCell)
            and isinstance(n.content, (ft.Row, ft.Column))
            and not getattr(n.content, "tight", False)
        ]
        assert not offenders, f"{route} has a non-tight {type(offenders[0].content).__name__} in a DataCell"
