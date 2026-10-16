"""StockWise — Settings view.

Store preferences (non-secret), database backups, and diagnostics. Secrets like
the TinyFish API key are read from the environment, never stored here.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.theme import StockWiseTheme as T
from repositories.sqlite.schema import SCHEMA_VERSION, get_schema_version
from ui.components.feedback import notify, notify_error
from ui.components.forms import text_field
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import action_cell, styled_table, text_cell


def build_settings_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    settings = app.settings.all()

    fields = {
        "shop_name": text_field("Shop name", value=settings.get("shop_name", ""), width=300),
        "currency": text_field("Currency", value=settings.get("currency", Config.DEFAULT_CURRENCY), width=150),
        "forecast_horizon_days": text_field("Forecast horizon (days)",
                                            value=settings.get("forecast_horizon_days", "7"), width=150),
        "review_period_days": text_field("Review period (days)",
                                         value=settings.get("review_period_days", "2"), width=150),
        "safety_buffer_days": text_field("Safety buffer (days)",
                                         value=settings.get("safety_buffer_days", "2"), width=150),
        "near_expiry_window_days": text_field("Near-expiry window (days)",
                                              value=settings.get("near_expiry_window_days", "7"), width=150),
    }

    def save(e) -> None:
        for key, field in fields.items():
            app.settings.set(key, (field.value or "").strip())
        notify(page, "Settings saved", "success")

    store_panel = section(
        "Store preferences",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            ft.Row(spacing=T.GAP_SMALL, wrap=True, controls=[fields["shop_name"], fields["currency"]]),
            ft.Row(spacing=T.GAP_SMALL, wrap=True, controls=[
                fields["forecast_horizon_days"], fields["review_period_days"],
                fields["safety_buffer_days"], fields["near_expiry_window_days"],
            ]),
            ft.Text("These preferences apply to forecasting and reorder logic in later stages.",
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY),
            ft.Button(content="Save settings", icon=ft.Icons.SAVE_OUTLINED, on_click=save),
        ]),
    )

    backups = app.backup_service.list_backups()
    backup_rows = [
        ft.DataRow(cells=[
            text_cell(path.name),
            text_cell(f"{path.stat().st_size / 1024:.0f} KB", color=T.TEXT_SECONDARY),
            action_cell(lambda e, p=path: _restore(page, navigate, p), icon=ft.Icons.RESTORE, tooltip="Restore"),
        ])
        for path in backups[:10]
    ]

    def backup_now(e) -> None:
        try:
            path = app.backup_service.create_backup()
            notify(page, f"Backup created: {path.name}", "success")
            navigate("/settings")
        except Exception as exc:  # pragma: no cover - filesystem errors
            notify_error(page, exc)

    backup_panel = section(
        "Backups",
        ft.Column(spacing=T.GAP, controls=[
            ft.Button(content="Back up now", icon=ft.Icons.CLOUD_UPLOAD_OUTLINED, on_click=backup_now),
            styled_table(["Backup file", "Size", ""], backup_rows, empty_message="No backups yet."),
        ]),
        subtitle=f"Saved to {Config.BACKUP_DIR}",
    )

    movement_count = app.db.query_one("SELECT COUNT(*) AS n FROM stock_movements")["n"]
    sales_count = app.db.query_one("SELECT COUNT(*) AS n FROM sales")["n"]
    diagnostics_panel = section(
        "Diagnostics",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            _kv("Database file", str(Config.DB_PATH)),
            _kv("Schema version", f"{get_schema_version(app.db)} (expected {SCHEMA_VERSION})"),
            _kv("Environment", Config.ENV),
            _kv("Active products", str(app.product_service.count_active())),
            _kv("Stock movements", str(movement_count)),
            _kv("Sales recorded", str(sales_count)),
            _kv("TinyFish configured", "Yes" if Config.TINYFISH_API_KEY else "No (optional)"),
        ]),
    )

    return scroll_column([
        page_header("Settings", "Preferences, backups and diagnostics"),
        store_panel,
        ft.Row(spacing=T.GAP, controls=[backup_panel, diagnostics_panel],
               vertical_alignment=ft.CrossAxisAlignment.START),
    ])


def _kv(label: str, value: str) -> ft.Control:
    return ft.Row(controls=[
        ft.Text(label, size=T.FONT_SMALL, color=T.TEXT_SECONDARY, width=170),
        ft.Text(value, size=T.FONT_SMALL, color=T.TEXT_PRIMARY, selectable=True),
    ])


def _restore(page: ft.Page, navigate: Callable[[str], None], path) -> None:
    app = app_context

    def do_restore(e) -> None:
        try:
            app.backup_service.restore_backup(path)
            page.pop_dialog()
            notify(page, "Database restored from backup", "success")
            navigate("/settings")
        except Exception as exc:  # pragma: no cover
            notify_error(page, exc)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("Restore database"),
        content=ft.Text(
            f"Replace the current database with '{path.name}'? "
            "Unsaved changes since that backup will be lost."
        ),
        actions=[
            ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
            ft.Button(content="Restore", on_click=do_restore),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
