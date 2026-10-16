"""StockWise — KPI card component.

A compact metric card used across the dashboard and detail screens. Values must
always come from real data (database/services) — never fabricated.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T


def _value_size(value: str) -> int:
    """Pick a display size that keeps long values (e.g. money) on one line.

    A KPI card is only ~1/4 of the content width, so strings such as
    ``₹1,23,456.00`` would otherwise wrap and break the card layout.
    """
    length = len(value)
    if length <= 10:
        return T.FONT_DISPLAY
    if length <= 13:
        return T.FONT_DISPLAY - 3
    if length <= 16:
        return T.FONT_DISPLAY - 7
    return T.FONT_DISPLAY - 10


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
            # ``no_wrap`` keeps money values such as ₹29,209.00 on a single line;
            # the size is scaled down for long strings so they still fit.
            ft.Text(
                value,
                size=_value_size(value),
                weight=ft.FontWeight.BOLD,
                color=T.TEXT_PRIMARY,
                no_wrap=True,
                max_lines=1,
            ),
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
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Container(
                    width=40,
                    height=40,
                    border_radius=T.RADIUS_SMALL,
                    bgcolor=ft.Colors.with_opacity(0.14, accent),
                    alignment=ft.Alignment.CENTER,
                    content=ft.Icon(icon, size=20, color=accent),
                ),
                text_column,
            ],
        ),
    )
