"""StockWise — Flet application entry point.

Bootstraps the backend (config, logging, database), then builds the persistent
shell: a left sidebar plus a top bar and a routed content area.

Run with:
    .venv\\Scripts\\flet.exe run main.py
    (or: .venv\\Scripts\\python.exe main.py)
"""

from __future__ import annotations

import logging

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.navigation import build_sidebar
from app.theme import StockWiseTheme as T
from ui.views.registry import build_view

logger = logging.getLogger(__name__)


def main(page: ft.Page) -> None:
    """Build and run the StockWise UI (Flet calls this with the Page)."""
    # --- Initialise backend ---
    try:
        app_context.initialize()
    except Exception as exc:  # pragma: no cover - surfaced to the user in-app
        logger.exception("Startup failed")
        page.add(ft.Text(f"Startup error: {exc}", color=T.STATUS_CRITICAL))
        return

    # --- Configure window / page ---
    page.title = f"{Config.APP_NAME} \u2014 {Config.APP_TAGLINE}"
    page.theme = T.get_flet_theme()
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = T.BG_DARKEST
    page.padding = 0
    page.spacing = 0
    try:
        page.window.width = Config.WINDOW_WIDTH
        page.window.height = Config.WINDOW_HEIGHT
        page.window.min_width = Config.MIN_WINDOW_WIDTH
        page.window.min_height = Config.MIN_WINDOW_HEIGHT
    except Exception:  # pragma: no cover - window API differs in web mode
        logger.debug("Window sizing unavailable in this Flet view mode")

    state: dict[str, str] = {"route": "/"}

    def navigate(route: str) -> None:
        state["route"] = route
        render()

    def build_top_bar() -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=T.CONTENT_PADDING, vertical=10),
            bgcolor=T.BG_DARKEST,
            border=ft.Border.only(bottom=ft.BorderSide(1, T.BORDER)),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.TextField(
                        hint_text="Search products, categories\u2026",
                        width=360,
                        height=40,
                        bgcolor=T.BG_INPUT,
                        text_size=T.FONT_BODY,
                        color=T.TEXT_PRIMARY,
                        hint_style=ft.TextStyle(color=T.TEXT_TERTIARY),
                        border={
                            ft.ControlState.DEFAULT: ft.OutlineInputBorder(
                                border_radius=ft.BorderRadius.all(T.INPUT_RADIUS),
                                side=ft.BorderSide(1, T.BORDER),
                            ),
                            ft.ControlState.FOCUSED: ft.OutlineInputBorder(
                                border_radius=ft.BorderRadius.all(T.INPUT_RADIUS),
                                side=ft.BorderSide(1, T.PRIMARY),
                            ),
                        },
                    ),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.NOTIFICATIONS_NONE, icon_color=T.TEXT_SECONDARY, icon_size=20),
                    ft.Container(width=8),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=32,
                                height=32,
                                border_radius=16,
                                bgcolor=T.PRIMARY,
                                alignment=ft.Alignment.CENTER,
                                content=ft.Icon(ft.Icons.PERSON, size=18, color=T.TEXT_ON_PRIMARY),
                            ),
                            ft.Text("Admin", size=T.FONT_BODY, color=T.TEXT_PRIMARY),
                        ],
                    ),
                ],
            ),
        )

    def render() -> None:
        page.controls.clear()
        content = build_view(state["route"], page, navigate)
        right_panel = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                build_top_bar(),
                ft.Container(content=content, expand=True, padding=T.CONTENT_PADDING),
            ],
        )
        layout = ft.Row(
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[build_sidebar(page, state["route"], navigate), right_panel],
        )
        page.add(layout)
        page.update()

    render()
    logger.info("StockWise UI loaded")


if __name__ == "__main__":
    ft.run(main)
