"""Shell smoke tests: the sidebar and every routed view build without a live page.

These validate Flet API usage (control construction) without launching a window.
"""

from __future__ import annotations

import flet as ft

from app.navigation import NAV_ITEMS, build_sidebar
from ui.views.registry import VIEW_META, build_view


class _StubPage:
    """Minimal stand-in for ft.Page during view construction."""

    def __init__(self) -> None:
        self.controls: list = []

    def add(self, *controls) -> None:  # pragma: no cover - not used during build
        self.controls.append(controls)

    def update(self) -> None:  # pragma: no cover - not used during build
        pass


def test_every_nav_route_has_view_meta():
    for route, _label, _icon in NAV_ITEMS:
        assert route in VIEW_META, f"Missing view meta for {route}"


def test_sidebar_builds():
    page = _StubPage()
    sidebar = build_sidebar(page, "/", lambda route: None)
    assert isinstance(sidebar, ft.Control)


def test_every_route_builds_a_view():
    page = _StubPage()
    for route, _label, _icon in NAV_ITEMS:
        view = build_view(route, page, lambda r: None)
        assert isinstance(view, ft.Control)
