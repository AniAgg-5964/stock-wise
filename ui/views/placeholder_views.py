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
from ui.components.layout import page_header  # re-exported for shared use


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
                    t("coming_soon"),
                    "This screen is part of a later stage and is not implemented yet.",
                    icon=icon,
                ),
            ),
        ],
    )
