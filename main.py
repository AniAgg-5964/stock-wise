"""StockWise — Flet application entry point.

Bootstraps the backend (config, logging, database), then builds the persistent
shell: a collapsible dark sidebar, a light top bar (global search, alerts, theme
switch) and a routed content area.

Run with:
    .venv\\Scripts\\flet.exe run main.py
    (or: .venv\\Scripts\\python.exe main.py)
"""

from __future__ import annotations

import logging

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.i18n import StockWiseLang as L, t
from app.navigation import build_sidebar, shop_name
from app.theme import StockWiseTheme as T
from ui.components.forms import search_field
from ui.components.status_chip import status_chip
from ui.views.registry import build_view

logger = logging.getLogger(__name__)

_ALERT_STATUS = {"critical": "critical", "warning": "near_expiry", "info": "info"}


def main(page: ft.Page) -> None:
    """Build and run the StockWise UI (Flet calls this with the Page)."""
    # --- Initialise backend ---
    try:
        app_context.initialize()
    except Exception as exc:  # pragma: no cover - surfaced to the user in-app
        logger.exception("Startup failed")
        page.add(ft.Text(f"Startup error: {exc}", color=T.STATUS_CRITICAL))
        return

    _restore_theme_preference(page)
    _restore_language_preference(page)

    # --- Configure window / page ---
    # Bundled fonts (Mukta: Latin + Devanagari). Loaded from the assets dir so the
    # app renders identically offline, with no network font fetch.
    page.fonts = dict(T.FONT_FILES)
    page.title = f"{Config.APP_NAME} \u2014 {Config.APP_TAGLINE}"
    page.theme = T.get_flet_theme()
    page.theme_mode = ft.ThemeMode.DARK if T.is_dark() else ft.ThemeMode.LIGHT
    page.bgcolor = T.PAGE_BG
    page.padding = 0
    page.spacing = 0
    try:
        page.window.width = Config.WINDOW_WIDTH
        page.window.height = Config.WINDOW_HEIGHT
        page.window.min_width = Config.MIN_WINDOW_WIDTH
        page.window.min_height = Config.MIN_WINDOW_HEIGHT
    except Exception:  # pragma: no cover - window API differs in web mode
        logger.debug("Window sizing unavailable in this Flet view mode")

    state: dict = {"route": "/", "collapsed": False, "panel": None, "query": ""}
    refs: dict = {"overlay": None}

    # ------------------------------------------------------------------ behaviour
    def navigate(route: str) -> None:
        state["route"] = route
        state["panel"] = None
        render()

    def toggle_sidebar() -> None:
        state["collapsed"] = not state["collapsed"]
        render()

    def toggle_theme() -> None:
        T.toggle()
        _persist_theme_preference(page, T.mode)
        page.theme = T.get_flet_theme()
        page.theme_mode = ft.ThemeMode.DARK if T.is_dark() else ft.ThemeMode.LIGHT
        page.bgcolor = T.PAGE_BG
        render()

    def toggle_language(mode: str) -> None:
        """Switch the UI language and re-render every screen.

        Frontend-only: no service, repository or schema change. Language is a
        reading preference, so it lives in client_storage beside the theme rather
        than in the settings table that drives forecasting.
        """
        L.apply(mode)
        _persist_language_preference(page, L.mode)
        render()

    def _lang_pill(label: str, code: str) -> ft.Control:
        """One half of the EN / हिन्दी switch; the active half is filled."""
        active = L.mode == code
        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=10, vertical=6),
            border_radius=T.RADIUS_SMALL - 2,
            bgcolor=T.PRIMARY if active else None,
            tooltip=t("topbar.toggle_language"),
            on_click=lambda e, c=code: toggle_language(c),
            ink=True,
            content=ft.Text(
                label, size=T.FONT_TINY,
                weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_400,
                color=T.TEXT_ON_PRIMARY if active else T.TEXT_SECONDARY,
            ),
        )

    def set_panel(panel: str | None) -> None:
        state["panel"] = panel
        show_overlay()

    def on_search(event: ft.ControlEvent) -> None:
        state["query"] = (event.control.value or "").strip()
        state["panel"] = "search" if state["query"] else None
        show_overlay()

    # -------------------------------------------------------------- overlay menu
    def _search_results() -> ft.Control:
        query = state["query"]
        try:
            products = app_context.product_service.list_products(active_only=True, search_query=query)
        except Exception:  # pragma: no cover - defensive
            products = []
        products = products[:6]
        if not products:
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=16),
                content=ft.Text(f"No products match \u201c{query}\u201d", size=T.FONT_SMALL,
                                color=T.TEXT_TERTIARY),
            )
        rows = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=T.RADIUS_SMALL,
                ink=True,
                on_click=lambda e, pid=p.id: navigate(f"/product/{pid}"),
                content=ft.Row(
                    spacing=10,
                    controls=[
                        ft.Icon(ft.Icons.INVENTORY_2_OUTLINED, size=16, color=T.TEXT_TERTIARY),
                        ft.Column(spacing=0, expand=True, controls=[
                            ft.Text(p.name, size=T.FONT_BODY, color=T.TEXT_PRIMARY,
                                    max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(f"{p.sku} \u00b7 {p.category}", size=T.FONT_TINY,
                                    color=T.TEXT_TERTIARY),
                        ]),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=T.TEXT_TERTIARY),
                    ],
                ),
            )
            for p in products
        ]
        return ft.Column(spacing=2, controls=[
            ft.Container(
                padding=ft.Padding.only(left=14, right=14, top=10, bottom=4),
                content=ft.Text(t("col.product"), size=T.FONT_TINY, weight=ft.FontWeight.W_600,
                                color=T.TEXT_TERTIARY),
            ),
            ft.Column(spacing=0, controls=rows),
        ])

    def _alerts_panel() -> ft.Control:
        try:
            alerts = app_context.alert_service.build()
        except Exception:  # pragma: no cover - defensive
            alerts = []
        alerts = alerts[:6]
        if not alerts:
            return ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=16),
                content=ft.Text(t("empty.no_alerts"), size=T.FONT_SMALL,
                                color=T.TEXT_TERTIARY),
            )
        rows = [
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=T.RADIUS_SMALL,
                ink=True,
                on_click=lambda e, r=a.route: navigate(r),
                content=ft.Row(
                    spacing=10,
                    controls=[
                        ft.Column(spacing=1, expand=True, controls=[
                            ft.Text(a.title, size=T.FONT_BODY, color=T.TEXT_PRIMARY, max_lines=1,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Text(a.message, size=T.FONT_TINY, color=T.TEXT_TERTIARY, max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS),
                        ]),
                        status_chip(a.severity.title(), _ALERT_STATUS.get(a.severity, "info")),
                    ],
                ),
            )
            for a in alerts
        ]
        return ft.Column(spacing=0, controls=rows)

    def show_overlay() -> None:
        overlay = refs.get("overlay")
        if overlay is None:
            return
        panel = state["panel"]
        if panel == "search":
            overlay.content = _search_results()
            overlay.width = 440
        elif panel == "alerts":
            overlay.content = _alerts_panel()
            overlay.width = 420
        overlay.visible = panel in ("search", "alerts")
        try:
            overlay.update()
        except Exception:  # pragma: no cover - control not mounted yet
            pass

    # --------------------------------------------------------------------- top bar
    def build_top_bar() -> ft.Control:
        def icon_button(icon: str, tooltip: str, on_click) -> ft.Control:
            return ft.IconButton(
                icon, icon_size=20, icon_color=T.TEXT_SECONDARY,
                tooltip=tooltip, on_click=lambda e: on_click(),
            )

        # Bell + live alert count badge.
        try:
            alert_count = len(app_context.alert_service.build())
        except Exception:  # pragma: no cover - defensive
            alert_count = 0
        bell = ft.Stack(
            controls=[
                icon_button(ft.Icons.NOTIFICATIONS_NONE, "Alerts",
                            lambda: set_panel(None if state["panel"] == "alerts" else "alerts")),
                ft.Container(
                    right=2, top=2,
                    width=17, height=17,
                    border_radius=9,
                    bgcolor=T.STATUS_CRITICAL,
                    alignment=ft.Alignment.CENTER,
                    visible=alert_count > 0,
                    content=ft.Text(str(alert_count), size=10, color=T.TEXT_ON_PRIMARY,
                                    weight=ft.FontWeight.BOLD),
                ),
            ]
        )

        search = search_field(
            t("topbar.search"),
            width=420,
            on_change=on_search,
        )

        return ft.Container(
            padding=ft.Padding.symmetric(horizontal=T.CONTENT_PADDING, vertical=13),
            bgcolor=T.TOPBAR_BG,
            border=ft.Border.only(bottom=ft.BorderSide(1, T.TOPBAR_BORDER)),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.IconButton(
                        ft.Icons.MENU, icon_size=20, icon_color=T.TEXT_SECONDARY,
                        tooltip=t("topbar.toggle_sidebar"),
                        on_click=lambda e: toggle_sidebar(),
                    ),
                    ft.Container(width=4),
                    search,
                    ft.Container(expand=True),
                    # Language switch, immediately left of the theme switch: the two
                    # are the only "how do I read this app" controls, so they sit
                    # together. A segmented control, not an icon — EN and हिन्दी are
                    # both short enough to show, and a globe icon would only say
                    # *that* a language exists, not which one is active.
                    ft.Container(
                        padding=2,
                        border_radius=T.RADIUS_SMALL,
                        bgcolor=T.BG_INPUT,
                        border=ft.Border.all(1, T.BORDER),
                        content=ft.Row(
                            spacing=0,
                            controls=[
                                _lang_pill("EN", "en"),
                                _lang_pill("हिन्दी", "hi"),
                            ],
                        ),
                    ),
                    ft.Container(width=8),
                    icon_button(
                        ft.Icons.DARK_MODE_OUTLINED if T.is_dark() else ft.Icons.LIGHT_MODE_OUTLINED,
                        t("topbar.toggle_theme"),
                        toggle_theme,
                    ),
                    ft.Container(
                        content=bell,
                        padding=ft.Padding.only(right=10),
                    ),
                    ft.Container(width=1, height=28, bgcolor=T.BORDER_SUBTLE),
                    ft.Container(width=10),
                    # Shop identity rather than a generic user avatar: this is a
                    # single-store app, so this is the shop, not a login account.
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border_radius=T.RADIUS_SMALL,
                        bgcolor=T.BG_HOVER,
                        content=ft.Row(
                            spacing=10,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Container(
                                    width=36,
                                    height=36,
                                    border_radius=18,
                                    bgcolor=T.PRIMARY,
                                    alignment=ft.Alignment.CENTER,
                                    content=ft.Icon(ft.Icons.STORE_OUTLINED, size=18,
                                                    color=T.TEXT_ON_PRIMARY),
                                ),
                                ft.Column(
                                    spacing=0,
                                    controls=[
                                        ft.Text(shop_name(), size=T.FONT_SMALL,
                                                weight=ft.FontWeight.W_600,
                                                color=T.TEXT_PRIMARY, no_wrap=True),
                                        ft.Text(t("topbar.store_owner"), size=T.FONT_TINY,
                                                color=T.TEXT_TERTIARY),
                                    ],
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        )

    # ------------------------------------------------------------------ error view
    def build_error_view(route: str, exc: Exception) -> ft.Control:
        """Friendly, recoverable fallback when a single screen fails to build."""
        return ft.Column(
            spacing=T.GAP,
            controls=[
                ft.Container(
                    padding=T.CARD_PADDING,
                    bgcolor=T.BG_CARD,
                    border_radius=T.RADIUS,
                    border=ft.Border.all(1, T.STATUS_CRITICAL),
                    shadow=T.shadow(),
                    content=ft.Column(spacing=T.GAP_SMALL, controls=[
                        ft.Row(spacing=8, controls=[
                            ft.Icon(ft.Icons.ERROR_OUTLINE, color=T.STATUS_CRITICAL, size=20),
                            ft.Text(t("topbar.error_title"), size=T.FONT_SUBTITLE,
                                    weight=ft.FontWeight.W_600, color=T.TEXT_PRIMARY),
                        ]),
                        ft.Text(f"Route '{route}' failed: {exc}", size=T.FONT_SMALL,
                                color=T.TEXT_SECONDARY, selectable=True),
                        ft.Text(t("topbar.error_body"),
                                size=T.FONT_SMALL, color=T.TEXT_TERTIARY),
                        ft.Row(spacing=T.GAP_SMALL, controls=[
                            ft.Button(content=t("topbar.go_dashboard"), icon=ft.Icons.DASHBOARD_OUTLINED,
                                      on_click=lambda e: navigate("/")),
                            ft.OutlinedButton(content=t("topbar.retry"), icon=ft.Icons.REFRESH,
                                              on_click=lambda e: render()),
                        ]),
                    ]),
                ),
            ],
        )

    # --------------------------------------------------------------------- render
    def render() -> None:
        page.controls.clear()
        try:
            content = build_view(state["route"], page, navigate)
        except Exception as exc:  # one broken screen must never break navigation
            logger.exception("Failed to build view for %s", state["route"])
            content = build_error_view(state["route"], exc)

        overlay = ft.Container(
            visible=False,
            width=440,
            top=T.TOPBAR_HEIGHT - 8,
            right=T.CONTENT_PADDING,
            bgcolor=T.BG_CARD,
            border_radius=T.RADIUS,
            border=ft.Border.all(1, T.BORDER),
            shadow=T.shadow(),
            padding=T.GAP_SMALL,
            content=ft.Column(spacing=0, controls=[]),
        )
        refs["overlay"] = overlay

        content_column = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                build_top_bar(),
                ft.Container(
                    content=content,
                    expand=True,
                    padding=T.CONTENT_PADDING,
                ),
            ],
        )
        right_panel = ft.Stack(
            expand=True,
            fit=ft.StackFit.EXPAND,
            controls=[content_column, overlay],
        )
        layout = ft.Row(
            expand=True,
            spacing=0,
            vertical_alignment=ft.CrossAxisAlignment.START,
            controls=[
                build_sidebar(page, state["route"], navigate, collapsed=state["collapsed"]),
                right_panel,
            ],
        )
        page.add(layout)
        show_overlay()
        page.update()

    render()
    logger.info("StockWise UI loaded")


def _restore_theme_preference(page: ft.Page) -> None:
    """Best-effort restore of the saved theme (frontend-only, never fatal)."""
    try:
        saved = page.client_storage.get("stockwise_theme")
        if saved in ("light", "dark"):
            T.apply(saved)
    except Exception:  # pragma: no cover - storage unavailable
        logger.debug("Theme preference unavailable")


def _persist_theme_preference(page: ft.Page, mode: str) -> None:
    try:
        page.client_storage.set("stockwise_theme", mode)
    except Exception:  # pragma: no cover - storage unavailable
        logger.debug("Could not persist theme preference")


def _restore_language_preference(page: ft.Page) -> None:
    """Best-effort restore of the saved language (frontend-only, never fatal)."""
    try:
        saved = page.client_storage.get("stockwise_lang")
        if saved in ("en", "hi"):
            L.apply(saved)
    except Exception:  # pragma: no cover - storage unavailable
        logger.debug("Language preference unavailable")


def _persist_language_preference(page: ft.Page, mode: str) -> None:
    try:
        page.client_storage.set("stockwise_lang", mode)
    except Exception:  # pragma: no cover - storage unavailable
        logger.debug("Could not persist language preference")


if __name__ == "__main__":
    # ``assets_dir`` is what makes page.fonts paths such as "/fonts/…ttf" resolve.
    ft.run(main, assets_dir=str(Config.ASSETS_DIR))
