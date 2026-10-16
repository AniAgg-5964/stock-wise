"""StockWise — feedback helpers (snackbars, banners).

Never leaves an action without feedback. Colour is always paired with text.
"""

from __future__ import annotations

import flet as ft

from app.theme import StockWiseTheme as T


def notify(page: ft.Page, message: str, kind: str = "info") -> None:
    """Show a transient snackbar with semantic colouring."""
    background = {
        "success": T.STATUS_HEALTHY,
        "error": T.STATUS_CRITICAL,
        "warning": T.STATUS_WARNING,
        "info": T.STATUS_INFO,
    }.get(kind, T.STATUS_INFO)
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(message, color=T.TEXT_ON_PRIMARY),
            bgcolor=background,
        )
    )


def notify_error(page: ft.Page, exc: Exception) -> None:
    """Show an error snackbar from an exception."""
    notify(page, str(exc), kind="error")


def banner(message: str, kind: str = "info") -> ft.Control:
    """An inline message banner (persistent, unlike a snackbar)."""
    color = {
        "success": T.STATUS_HEALTHY,
        "error": T.STATUS_CRITICAL,
        "warning": T.STATUS_WARNING,
        "info": T.STATUS_INFO,
    }.get(kind, T.STATUS_INFO)
    icon = {
        "success": ft.Icons.CHECK_CIRCLE_OUTLINE,
        "error": ft.Icons.ERROR_OUTLINE,
        "warning": ft.Icons.WARNING_AMBER_OUTLINED,
        "info": ft.Icons.INFO_OUTLINE,
    }.get(kind, ft.Icons.INFO_OUTLINE)
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=T.RADIUS_SMALL,
        bgcolor=ft.Colors.with_opacity(0.12, color),
        border=ft.Border.all(1, ft.Colors.with_opacity(0.35, color)),
        content=ft.Row(
            spacing=8,
            controls=[
                ft.Icon(icon, size=16, color=color),
                ft.Text(message, size=T.FONT_SMALL, color=T.TEXT_PRIMARY, expand=True),
            ],
        ),
    )
