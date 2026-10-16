"""StockWise — Sidebar navigation.

Single source of truth for the sidebar destinations and the sidebar widget.
The sidebar is persistent on every screen (per the UI/UX spec).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.theme import StockWiseTheme as T

# (route, label, icon) — order defines the sidebar order.
NAV_ITEMS: list[tuple[str, str, str]] = [
    ("/", "Dashboard", ft.Icons.DASHBOARD_OUTLINED),
    ("/inventory", "Inventory", ft.Icons.INVENTORY_2_OUTLINED),
    ("/sales", "Sales", ft.Icons.POINT_OF_SALE_OUTLINED),
    ("/forecasting", "Forecasting", ft.Icons.INSIGHTS_OUTLINED),
    ("/reorder", "Reorder Center", ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED),
    ("/expiry", "Expiry Management", ft.Icons.EVENT_BUSY_OUTLINED),
    ("/suppliers", "Supplier Research", ft.Icons.STOREFRONT_OUTLINED),
    ("/reports", "Reports", ft.Icons.BAR_CHART_OUTLINED),
    ("/settings", "Settings", ft.Icons.SETTINGS_OUTLINED),
]


def _brand_header() -> ft.Control:
    return ft.Container(
        padding=ft.Padding.only(left=20, right=20, top=22, bottom=18),
        content=ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=36,
                    height=36,
                    border_radius=T.RADIUS_SMALL,
                    bgcolor=T.PRIMARY,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(ft.Icons.INVENTORY, size=20, color=T.TEXT_ON_PRIMARY),
                ),
                ft.Column(
                    spacing=0,
                    controls=[
                        ft.Text("StockWise", size=T.FONT_SUBTITLE, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
                        ft.Text("Smarter Stock", size=T.FONT_TINY, color=T.TEXT_TERTIARY),
                    ],
                ),
            ],
        ),
    )


def _nav_item(route: str, label: str, icon: str, current_route: str, on_navigate: Callable[[str], None]) -> ft.Control:
    selected = route == current_route
    return ft.Container(
        height=42,
        border_radius=T.RADIUS_SMALL,
        padding=ft.Padding.symmetric(horizontal=12),
        margin=ft.Margin.symmetric(horizontal=10, vertical=2),
        bgcolor=T.PRIMARY_SUBTLE if selected else None,
        on_click=lambda e, r=route: on_navigate(r),
        ink=True,
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(icon, size=18, color=T.PRIMARY if selected else T.TEXT_SECONDARY),
                ft.Text(
                    label,
                    size=T.FONT_BODY,
                    color=T.TEXT_PRIMARY if selected else T.TEXT_SECONDARY,
                    weight=ft.FontWeight.W_600 if selected else ft.FontWeight.NORMAL,
                ),
            ],
        ),
    )


def build_sidebar(page: ft.Page, current_route: str, on_navigate: Callable[[str], None]) -> ft.Control:
    """Build the persistent left sidebar."""
    # Product detail pages keep "Inventory" highlighted.
    effective_route = "/inventory" if current_route.startswith("/product/") else current_route
    items = [_nav_item(route, label, icon, effective_route, on_navigate) for route, label, icon in NAV_ITEMS]
    return ft.Container(
        width=T.SIDEBAR_WIDTH,
        bgcolor=T.BG_DARK,
        border=ft.Border.only(right=ft.BorderSide(1, T.BORDER)),
        content=ft.Column(
            spacing=0,
            controls=[
                _brand_header(),
                ft.Divider(height=1, thickness=1, color=T.BORDER_SUBTLE),
                ft.Container(height=8),
                ft.Column(spacing=0, controls=items),
                ft.Container(expand=True),
                ft.Container(
                    padding=ft.Padding.only(left=20, right=20, top=12, bottom=16),
                    content=ft.Text("Offline-first \u00b7 v0.1.0", size=T.FONT_TINY, color=T.TEXT_TERTIARY),
                ),
            ],
        ),
    )
