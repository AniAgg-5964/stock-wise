"""StockWise — placeholder views (Stage 1 shell).

These are honest "not implemented yet" screens so navigation works end-to-end
before the data layer exists. Real views replace them in later stages; they
never fabricate numbers.
"""

from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.theme import StockWiseTheme as T
from ui.components.empty_state import empty_state


def page_header(title: str, subtitle: Optional[str] = None, actions: Optional[list[ft.Control]] = None) -> ft.Control:
    """Standard page header (title + optional subtitle + right-aligned actions)."""
    left = ft.Column(
        spacing=2,
        controls=[
            ft.Text(title, size=T.FONT_TITLE, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY),
        ],
    )
    if subtitle:
        left.controls.append(ft.Text(subtitle, size=T.FONT_SMALL, color=T.TEXT_SECONDARY))

    controls: list[ft.Control] = [left, ft.Container(expand=True)]
    if actions:
        controls.append(ft.Row(spacing=8, controls=actions))
    return ft.Container(padding=ft.Padding.only(bottom=T.GAP), content=ft.Row(
        vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=controls
    ))


def build_placeholder_view(
    page: ft.Page,
    navigate: Callable[[str], None],
    *,
    title: str,
    description: str,
    icon: str,
) -> ft.Control:
    """Build a titled placeholder screen."""
    return ft.Column(
        expand=True,
        spacing=0,
        controls=[
            page_header(title, description),
            ft.Container(
                expand=True,
                bgcolor=T.BG_CARD,
                border_radius=T.RADIUS,
                border=ft.Border.all(1, T.BORDER_SUBTLE),
                content=empty_state(
                    "Coming soon",
                    "This screen is part of a later stage and is not implemented yet.",
                    icon=icon,
                ),
            ),
        ],
    )
