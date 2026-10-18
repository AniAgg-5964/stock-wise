"""StockWise — feedback helpers (snackbars, banners).

Never leaves an action without feedback. Colour is always paired with text.

Messages are rounded and carry an icon rather than being a full-width colour
block: a shopkeeper glancing at the screen mid-task should read what happened
without having to parse a saturated banner.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T

_KIND_COLOR = {
    "success": lambda: T.STATUS_HEALTHY,
    "error": lambda: T.STATUS_CRITICAL,
    "warning": lambda: T.STATUS_WARNING,
    "info": lambda: T.STATUS_INFO,
}

_KIND_ICON = {
    "success": ft.Icons.CHECK_CIRCLE_OUTLINE,
    "error": ft.Icons.ERROR_OUTLINE,
    "warning": ft.Icons.WARNING_AMBER_OUTLINED,
    "info": ft.Icons.INFO_OUTLINE,
}


def _color_for(kind: str):
    return _KIND_COLOR.get(kind, _KIND_COLOR["info"])()


def notify(page: ft.Page, message: str, kind: str = "info") -> None:
    """Show a transient snackbar with semantic colouring."""
    color = _color_for(kind)
    page.show_dialog(
        ft.SnackBar(
            bgcolor=color,
            content=ft.Row(
                spacing=10,
                tight=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(_KIND_ICON.get(kind, ft.Icons.INFO_OUTLINE), size=19,
                            color=T.TEXT_ON_PRIMARY),
                    ft.Text(message, color=T.TEXT_ON_PRIMARY, size=T.FONT_BODY, weight=ft.FontWeight.W_500),
                ],
            ),
        )
    )


def notify_error(page: ft.Page, exc: Exception) -> None:
    """Show an error snackbar from an exception."""
    notify(page, str(exc), kind="error")


def banner(message: str, kind: str = "info") -> ft.Control:
    """An inline message (persistent, unlike a snackbar).

    A tinted strip with a left accent rule rather than a fully outlined box: the
    banner is a note inside a page, and drawing all four edges around it was one
    more competing surface.
    """
    color = _color_for(kind)
    return ft.Container(
        padding=ft.Padding.only(left=14, right=14, top=12, bottom=12),
        border_radius=T.RADIUS_SMALL,
        bgcolor=ft.Colors.with_opacity(0.10, color),
        border=ft.Border.only(left=ft.BorderSide(3, color)),
        content=ft.Row(
            spacing=10,
            controls=[
                ft.Icon(_KIND_ICON.get(kind, ft.Icons.INFO_OUTLINE), size=18, color=color),
                ft.Text(message, size=T.FONT_BODY, color=T.TEXT_PRIMARY, expand=True),
            ],
        ),
    )
