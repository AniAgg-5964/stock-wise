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
            width=56,
            height=56,
            border_radius=28,
            bgcolor=T.BG_INPUT,
            alignment=ft.Alignment.CENTER,
            content=ft.Icon(icon, size=26, color=T.TEXT_TERTIARY),
        ),
        ft.Container(height=12),
        ft.Text(title, size=T.FONT_SUBTITLE, weight=ft.FontWeight.W_600, color=T.TEXT_PRIMARY),
        ft.Container(height=4),
        ft.Text(message, size=T.FONT_BODY, color=T.TEXT_SECONDARY, text_align=ft.TextAlign.CENTER),
    ]
    if action is not None:
        children += [ft.Container(height=16), action]
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=T.CONTENT_PADDING,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=0,
            controls=children,
        ),
    )
