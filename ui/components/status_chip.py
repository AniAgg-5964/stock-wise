"""StockWise — status chip component.

A small coloured pill. Colour is always paired with a text label (never colour
alone), per the accessibility rules in the UI/UX spec.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T


def status_chip(label: str, status: str = "info", *, icon: str | None = None) -> ft.Control:
    """Build a status pill; ``status`` is a semantic keyword (see ``T.status_color``)."""
    color = T.status_color(status)
    controls: list[ft.Control] = []
    if icon:
        controls.append(ft.Icon(icon, size=12, color=color))
    controls.append(ft.Text(label, size=T.FONT_TINY, color=color, weight=ft.FontWeight.W_600))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=T.RADIUS_SMALL,
        bgcolor=ft.Colors.with_opacity(0.14, color),
        content=ft.Row(spacing=5, tight=True, controls=controls),
    )
