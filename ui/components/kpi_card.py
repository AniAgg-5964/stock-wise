"""StockWise — KPI card component.

A compact metric card used across the dashboard and detail screens. Values must
always come from real data (database/services) — never fabricated.
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
    accent: str | None = None,
    on_click: Optional[Callable] = None,
    delta: Optional[str] = None,
    delta_kind: str = "muted",
    col=None,
) -> ft.Control:
    """Build a single KPI card: icon tile, label, large value, caption.

    Pass ``col`` when placing cards in a ``ResponsiveRow`` so they reflow.
    """
    accent = accent or T.PRIMARY
    caption = delta if delta is not None else subtitle
    caption_color = {
        "up": T.STATUS_HEALTHY,
        "down": T.STATUS_CRITICAL,
        "info": T.STATUS_INFO,
        "warn": T.STATUS_WARNING,
        "muted": T.TEXT_TERTIARY,
    }.get(delta_kind, T.TEXT_TERTIARY)

    text_column = ft.Column(
        spacing=2,
        expand=True,
        controls=[
            ft.Text(title, size=T.FONT_SMALL, color=T.TEXT_SECONDARY, weight=ft.FontWeight.W_500),
            ft.Text(value, size=T.FONT_DISPLAY, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
        ],
    )
    if caption:
        text_column.controls.append(
            ft.Text(caption, size=T.FONT_SMALL, color=caption_color, weight=ft.FontWeight.W_500)
        )

    return ft.Container(
        expand=col is None,
        col=col,
        padding=T.CARD_PADDING,
        bgcolor=T.BG_CARD,
        border_radius=T.RADIUS,
        border=ft.Border.all(1, T.BORDER_SUBTLE),
        shadow=T.shadow(),
        on_click=on_click,
        ink=on_click is not None,
        content=ft.Row(
            spacing=T.GAP,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=44,
                    height=44,
                    border_radius=T.RADIUS_SMALL,
                    bgcolor=ft.Colors.with_opacity(0.14, accent),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon, size=22, color=accent),
                ),
                text_column,
            ],
        ),
    )
