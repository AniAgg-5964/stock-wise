"""StockWise — Sidebar navigation.

Single source of truth for the sidebar destinations and the sidebar widget.

The sidebar is the app's main navigation and stays put on every screen. It is the
one place the brand green runs at full strength, which anchors the whole app and
separates "where I am" from "what I'm looking at".

Ten destinations in one undifferentiated list is a lot to read, so they are
grouped into what a shopkeeper actually does: check the shop, make decisions,
then everything else. ``NAV_GROUPS`` is the source of truth; ``NAV_ITEMS`` is the
flat form kept for tests and for iterating a single row of items.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.i18n import t
from app.theme import StockWiseTheme as T

# (group heading key, [(route, label key, icon), ...]). Labels are translation
# *keys*, not English text: the sidebar is the one screen a shopkeeper reads on
# every visit, so it has to resolve at build time in whichever language is active.
NAV_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("", [
        ("/", "nav.dashboard", ft.Icons.SPACE_DASHBOARD_OUTLINED),
    ]),
    ("nav.group.shop", [
        ("/inventory", "nav.inventory", ft.Icons.INVENTORY_2_OUTLINED),
        ("/sales", "nav.sales", ft.Icons.POINT_OF_SALE_OUTLINED),
        ("/expiry", "nav.expiry", ft.Icons.EVENT_BUSY_OUTLINED),
    ]),
    ("nav.group.decisions", [
        ("/forecasting", "nav.forecasting", ft.Icons.INSIGHTS_OUTLINED),
        ("/reorder", "nav.reorder", ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED),
        ("/suppliers", "nav.suppliers", ft.Icons.STOREFRONT_OUTLINED),
    ]),
    ("nav.group.more", [
        ("/reports", "nav.reports", ft.Icons.BAR_CHART_OUTLINED),
        ("/data", "nav.data", ft.Icons.SWAP_VERT),
        ("/settings", "nav.settings", ft.Icons.SETTINGS_OUTLINED),
    ]),
]

# Flat (route, label, icon) list. Routes must never change: the alert service
# emits route strings that the dashboard navigates to, and the view registry is
# keyed on them.
NAV_ITEMS: list[tuple[str, str, str]] = [
    item for _heading, group in NAV_GROUPS for item in group
]


def shop_name() -> str:
    """The configured shop name, or a friendly fallback.

    Public because the top bar shows the same identity as the sidebar store card.
    """
    try:
        from app.bootstrap import app_context

        return (app_context.settings.get("shop_name") or "").strip() or t("brand.my_store")
    except Exception:  # never block the chrome on a settings read
        return t("brand.my_store")


def _brand_header(collapsed: bool) -> ft.Control:
    # A cream tile on deep green: the one bright mark that makes the brand
    # instantly identifiable without shouting.
    logo = ft.Container(
        width=42,
        height=42,
        border_radius=T.RADIUS_SMALL,
        bgcolor=T.BG_CARD,
        alignment=ft.Alignment.CENTER,
        content=ft.Icon(ft.Icons.STORE_OUTLINED, size=22, color=T.PRIMARY),
    )
    if collapsed:
        return ft.Container(
            padding=ft.Padding.symmetric(vertical=20),
            alignment=ft.Alignment.CENTER,
            content=logo,
        )
    return ft.Container(
        padding=ft.Padding.only(left=20, right=20, top=22, bottom=18),
        content=ft.Row(
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                logo,
                ft.Column(
                    spacing=1,
                    expand=True,
                    controls=[
                        ft.Text(
                            t("brand.name"), size=T.FONT_SUBTITLE, weight=ft.FontWeight.BOLD,
                            color=T.SIDEBAR_TEXT_ACTIVE, font_family=T.FONT_FAMILY_BOLD,
                            no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        ft.Text(
                            t("brand.tagline"), size=T.FONT_TINY,
                            color=T.SIDEBAR_MUTED, no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                    ],
                ),
            ],
        ),
    )


def _group_heading(key: str, collapsed: bool) -> ft.Control | None:
    text = t(key)
    if collapsed or not text:
        return None
    return ft.Container(
        padding=ft.Padding.only(left=24, right=12, top=12, bottom=4),
        content=ft.Text(
            text.upper(), size=T.FONT_TINY - 1, color=T.SIDEBAR_MUTED,
            weight=ft.FontWeight.W_600, no_wrap=True,
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

    icon_control = ft.Icon(icon, size=20, color=T.SIDEBAR_TEXT_ACTIVE if selected else T.SIDEBAR_TEXT)
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
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
            ],
        )

    return ft.Container(
        height=42,
        border_radius=T.RADIUS_SMALL,
        padding=ft.Padding.symmetric(horizontal=14),
        margin=ft.Margin.symmetric(horizontal=12, vertical=1),
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
            padding=ft.Padding.only(bottom=18),
            alignment=ft.Alignment.CENTER,
            content=ft.Container(
                width=42,
                height=42,
                border_radius=T.RADIUS_SMALL,
                bgcolor=T.SIDEBAR_CARD_BG,
                alignment=ft.Alignment.CENTER,
                tooltip=shop_name,
                content=ft.Icon(ft.Icons.STOREFRONT_OUTLINED, size=20, color=T.SIDEBAR_TEXT_ACTIVE),
            ),
        )
    return ft.Container(
        margin=ft.Margin.symmetric(horizontal=14, vertical=14),
        padding=ft.Padding.symmetric(horizontal=14, vertical=13),
        border_radius=T.RADIUS_SMALL,
        bgcolor=T.SIDEBAR_CARD_BG,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=36,
                            height=36,
                            border_radius=T.RADIUS_SMALL,
                            bgcolor=ft.Colors.with_opacity(0.18, T.BG_CARD),
                            alignment=ft.Alignment.CENTER,
                            content=ft.Icon(ft.Icons.STOREFRONT_OUTLINED, size=18,
                                            color=T.SIDEBAR_TEXT_ACTIVE),
                        ),
                        ft.Column(
                            spacing=1,
                            expand=True,
                            controls=[
                                ft.Text(shop_name, size=T.FONT_SMALL, weight=ft.FontWeight.W_600,
                                        color=T.SIDEBAR_TEXT_ACTIVE, no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(t("brand.single_store"), size=T.FONT_TINY, color=T.SIDEBAR_MUTED),
                            ],
                        ),
                    ],
                ),
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=T.STATUS_HEALTHY),
                        ft.Text(t("brand.offline"), size=T.FONT_TINY, color=T.SIDEBAR_TEXT,
                                weight=ft.FontWeight.W_500),
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
    """Build the persistent left sidebar (deep brand green, collapsible)."""
    # Product detail pages keep "Inventory" highlighted.
    effective_route = "/inventory" if current_route.startswith("/product/") else current_route

    groups: list[ft.Control] = [ft.Container(height=6)]
    for heading, items in NAV_GROUPS:
        group_heading = _group_heading(heading, collapsed)
        if group_heading is not None:
            groups.append(group_heading)
        groups.append(
            ft.Column(
                spacing=0,
                controls=[
                    _nav_item(route, t(key), icon, effective_route, on_navigate, collapsed)
                    for route, key, icon in items
                ],
            )
        )

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
                    bgcolor=ft.Colors.with_opacity(0.35, T.SIDEBAR_BORDER),
                    margin=ft.Margin.symmetric(horizontal=20),
                ),
                # Scrollable: the grouped list is taller than a 768px window at
                # its smallest, and the window can be resized down further.
                ft.Column(spacing=0, controls=groups, scroll=ft.ScrollMode.AUTO, expand=True),
                _store_card(collapsed, shop_name()),
            ],
        ),
    )
