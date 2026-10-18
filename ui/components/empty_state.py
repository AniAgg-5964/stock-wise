"""StockWise — empty-state component.

Shown instead of blank panels when a screen has no data yet, or when a feature
is not implemented. Never leaves a blank panel.
"""

from __future__ import annotations

from typing import Optional

import flet as ft

from app.theme import StockWiseTheme as T


def empty_state(
    title: str,
    message: str,
    *,
    icon: str = ft.Icons.INBOX_OUTLINED,
    action: Optional[ft.Control] = None,
) -> ft.Control:
    """Build a centred empty-state panel."""
    children: list[ft.Control] = [
        ft.Container(
            width=64,
            height=64,
            border_radius=32,
            bgcolor=T.TINT_HEALTHY if icon == ft.Icons.CHECK_CIRCLE_OUTLINE else T.BG_INPUT,
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(icon, size=30,
                            color=T.STATUS_HEALTHY if icon == ft.Icons.CHECK_CIRCLE_OUTLINE
                            else T.TEXT_TERTIARY),
        ),
        ft.Container(height=16),
        ft.Text(title, size=T.FONT_SUBTITLE, weight=ft.FontWeight.W_600, color=T.TEXT_PRIMARY,
                text_align=ft.TextAlign.CENTER),
        ft.Container(height=6),
        ft.Text(message, size=T.FONT_BODY, color=T.TEXT_SECONDARY, text_align=ft.TextAlign.CENTER),
    ]
    if action is not None:
        children += [ft.Container(height=18), action]
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.symmetric(vertical=40, horizontal=T.CONTENT_PADDING),
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=0,
            controls=children,
        ),
    )
