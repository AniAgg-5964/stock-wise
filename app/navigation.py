"""StockWise — Sidebar navigation.

Single source of truth for the sidebar destinations and the sidebar widget.
The sidebar is persistent on every screen and can collapse to an icon-only rail.
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
    ("/data", "Data & Imports", ft.Icons.SWAP_VERT),
    ("/settings", "Settings", ft.Icons.SETTINGS_OUTLINED),
]


def _shop_name() -> str:
    try:
        from app.bootstrap import app_context

        return (app_context.settings.get("shop_name") or "").strip() or "My Store"
    except Exception:  # never block the sidebar on a settings read
        return "My Store"


def _brand_header(collapsed: bool) -> ft.Control:
    logo = ft.Container(
        width=38,
        height=38,
        border_radius=T.RADIUS_SMALL,
        bgcolor=T.PRIMARY,
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(ft.Icons.INVENTORY, size=20, color=T.TEXT_ON_PRIMARY),
    )
    if collapsed:
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=18),
            alignment=ft.Alignment.CENTER,
            content=logo,
        )
    return ft.Container(
        padding=ft.Padding.only(left=18, right=18, top=20, bottom=16),
        content=ft.Row(
            spacing=11,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                logo,
                ft.Column(
                    spacing=0,
                    controls=[
                        ft.Text("StockWise", size=T.FONT_SUBTITLE, weight=ft.FontWeight.BOLD,
                                color=T.SIDEBAR_TEXT_ACTIVE),
                        ft.Text("Smarter Stock. Less Waste.", size=T.FONT_TINY, color=T.SIDEBAR_MUTED),
                    ],
                ),
            ],
        ),
    )


def _nav_item(
    route: str,
    label: str,
    icon: str,
    current_route: str,
    on_navigate: Callable[[str], None],
    collapsed: bool,
) -> ft.Control:
    selected = route == current_route

    def _on_hover(event: ft.ControlEvent) -> None:
        hovered = str(event.data).lower() == "true" and not selected
        event.control.bgcolor = T.SIDEBAR_HOVER_BG if hovered else (
            T.SIDEBAR_ACTIVE_BG if selected else None
        )
        event.control.update()

    icon_control = ft.Icon(icon, size=19, color=T.SIDEBAR_TEXT_ACTIVE if selected else T.SIDEBAR_TEXT)
    body: ft.Control = icon_control
    if not collapsed:
        body = ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                icon_control,
                ft.Text(
                    label,
                    size=T.FONT_BODY,
                    color=T.SIDEBAR_TEXT_ACTIVE if selected else T.SIDEBAR_TEXT,
                    weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400,
                    no_wrap=True,
                ),
            ],
        )

    return ft.Container(
        height=42,
        border_radius=T.RADIUS_SMALL,
        padding=ft.Padding.symmetric(horizontal=12),
        margin=ft.Margin.symmetric(horizontal=10, vertical=2),
        bgcolor=T.SIDEBAR_ACTIVE_BG if selected else None,
        alignment=ft.Alignment.CENTER if collapsed else None,
        tooltip=label if collapsed else None,
        on_click=lambda e, r=route: on_navigate(r),
        on_hover=_on_hover,
        ink=False,
        content=body,
    )


def _store_card(collapsed: bool, shop_name: str) -> ft.Control:
    if collapsed:
        return ft.Container(
            padding=ft.Padding.only(bottom=16),
            alignment=ft.Alignment.CENTER,
            content=ft.Container(
                width=38,
                height=38,
                border_radius=T.RADIUS_SMALL,
                bgcolor=T.SIDEBAR_CARD_BG,
                alignment=ft.Alignment.CENTER,
                tooltip=shop_name,
                content=ft.Icon(ft.Icons.STOREFRONT_OUTLINED, size=19, color=T.SIDEBAR_TEXT_ACTIVE),
            ),
        )
    return ft.Container(
        margin=ft.Margin.symmetric(horizontal=12, vertical=12),
        padding=ft.Padding.symmetric(horizontal=12, vertical=11),
        border_radius=T.RADIUS_SMALL,
        bgcolor=T.SIDEBAR_CARD_BG,
        content=ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=34,
                            height=34,
                            border_radius=T.RADIUS_SMALL,
                            bgcolor=T.PRIMARY,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(ft.Icons.STOREFRONT_OUTLINED, size=17,
                                            color=T.TEXT_ON_PRIMARY),
                        ),
                        ft.Column(
                            spacing=0,
                            expand=True,
                            controls=[
                                ft.Text(shop_name, size=T.FONT_SMALL, weight=ft.FontWeight.W_600,
                                        color=T.SIDEBAR_TEXT_ACTIVE, no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text("Single store (MVP)", size=T.FONT_TINY, color=T.SIDEBAR_MUTED),
                            ],
                        ),
                    ],
                ),
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Container(width=7, height=7, border_radius=4, bgcolor=T.STATUS_HEALTHY),
                        ft.Text("Online", size=T.FONT_TINY, color=T.SIDEBAR_TEXT, weight=ft.FontWeight.W_500),
                    ],
                ),
            ],
        ),
    )


def build_sidebar(
    page: ft.Page,
    current_route: str,
    on_navigate: Callable[[str], None],
    *,
    collapsed: bool = False,
) -> ft.Control:
    """Build the persistent left sidebar (dark navy, collapsible)."""
    # Product detail pages keep "Inventory" highlighted.
    effective_route = "/inventory" if current_route.startswith("/product/") else current_route
    items = [
        _nav_item(route, label, icon, effective_route, on_navigate, collapsed)
        for route, label, icon in NAV_ITEMS
    ]
    return ft.Container(
        width=T.SIDEBAR_WIDTH_COLLAPSED if collapsed else T.SIDEBAR_WIDTH,
        bgcolor=T.SIDEBAR_BG,
        border=ft.Border.only(right=ft.BorderSide(1, T.SIDEBAR_BORDER)),
        content=ft.Column(
            spacing=0,
            controls=[
                _brand_header(collapsed),
                ft.Container(
                    height=1,
                    bgcolor=T.SIDEBAR_BORDER,
                    margin=ft.Margin.symmetric(horizontal=12),
                ),
                ft.Container(height=10),
                ft.Column(spacing=0, controls=items),
                ft.Container(expand=True),
                _store_card(collapsed, _shop_name()),
            ],
        ),
    )
