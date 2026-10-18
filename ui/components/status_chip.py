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
    tint = T.tint_for(status)
    controls: list[ft.Control] = []
    if icon:
        controls.append(ft.Icon(icon, size=14, color=color))
    controls.append(ft.Text(label, size=T.FONT_TINY, color=color, weight=ft.FontWeight.W_600))
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=11, vertical=5),
        border_radius=T.CHIP_RADIUS,
        bgcolor=tint,
        content=ft.Row(spacing=5, tight=True, vertical_alignment=ft.CrossAxisAlignment.CENTER,
                       controls=controls),
    )
