"""StockWise — KPI card component.

A compact metric card used on the dashboard. Values must always come from real
data (database/services) — never fabricated.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T


def kpi_card(
    title: str,
    value: str,
    *,
    subtitle: Optional[str] = None,
    icon: str = ft.Icons.ANALYTICS_OUTLINED,
    accent: str = T.PRIMARY,
    on_click: Optional[Callable] = None,
) -> ft.Control:
    """Build a single KPI card."""
    value_row = ft.Row(
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(value, size=T.FONT_DISPLAY, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
        ],
    )

    children: list[ft.Control] = [
        ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                ft.Text(title, size=T.FONT_SMALL, color=T.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
                ft.Container(
                    width=34,
                    height=34,
                    border_radius=T.RADIUS_SMALL,
                    bgcolor=ft.Colors.with_opacity(0.14, accent),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon, size=18, color=accent),
                ),
            ],
        ),
        ft.Container(height=6),
        value_row,
    ]
    if subtitle:
        children.append(ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY))

    return ft.Container(
        expand=True,
        padding=T.CARD_PADDING,
        bgcolor=T.BG_CARD,
        border_radius=T.RADIUS,
        border=ft.Border.all(1, T.BORDER_SUBTLE),
        on_click=on_click,
        ink=on_click is not None,
        content=ft.Column(spacing=2, controls=children),
    )
