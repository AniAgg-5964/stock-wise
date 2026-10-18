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
from app.i18n import t
from repositories.sqlite.schema import SCHEMA_VERSION, get_schema_version
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.layout import flow_row, page_header, panel_grid, scroll_column, section
from ui.components.table import action_cell, styled_table, text_cell

_BASELINE_OPTIONS = [
    ("best", "Best baseline per product"),
    ("seasonal_naive", "Seasonal naive (same weekday)"),
    ("moving_average", "7-day moving average"),
    ("mean", "Average demand"),
]

_SAFETY_POLICY_OPTIONS = [
    ("heuristic", "Heuristic (average demand x buffer days)"),
    ("statistical", "Statistical (service level x variability)"),
]

_SERVICE_LEVEL_OPTIONS = [
    ("0.80", "80%"), ("0.85", "85%"), ("0.90", "90% (default)"),
    ("0.95", "95%"), ("0.98", "98%"), ("0.99", "99%"),
]


def build_settings_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    settings = app.settings.all()

    fields = {
        "shop_name": text_field(t("field.shop_name"), value=settings.get("shop_name", ""), width=300),
        "currency": text_field(t("field.currency"), value=settings.get("currency", Config.DEFAULT_CURRENCY), width=150),
        "forecast_horizon_days": text_field(t("field.forecast_horizon"),
                                            value=settings.get("forecast_horizon_days", "7"), width=150),
        "review_period_days": text_field(t("field.review_period"),
                                         value=settings.get("review_period_days", "2"), width=150),
        "safety_buffer_days": text_field(t("field.safety_buffer"),
                                         value=settings.get("safety_buffer_days", "2"), width=150),
        "near_expiry_window_days": text_field(t("field.expiry_window"),
                                              value=settings.get("near_expiry_window_days", "7"), width=150),
        "purchase_budget": text_field(t("field.purchase_budget"),
                                      value=settings.get("purchase_budget", ""), width=220),
    }

    policy_fields = {
        "forecast_baseline_method": dropdown_field(
            t("field.baseline_fallback"), _BASELINE_OPTIONS,
            value=settings.get("forecast_baseline_method", "best"), width=320),
        "safety_policy": dropdown_field(
            t("field.safety_policy"), _SAFETY_POLICY_OPTIONS,
            value=settings.get("safety_policy", "heuristic"), width=340),
        "service_level": dropdown_field(
            t("field.service_level"), _SERVICE_LEVEL_OPTIONS,
            value=settings.get("service_level", "0.90"), width=320),
    }

    def save(e) -> None:
        for key, field in fields.items():
            app.settings.set(key, (field.value or "").strip())
        for key, field in policy_fields.items():
            app.settings.set(key, (field.value or "").strip())
        notify(page, t("toast.settings_saved"), "success")

    store_panel = section(
        t("panel.store_preferences"),
        ft.Column(spacing=T.GAP_SMALL, controls=[
            flow_row([fields["shop_name"], fields["currency"]], col={"xs": 12, "sm": 6, "lg": 4}),
            flow_row([
                fields["forecast_horizon_days"], fields["review_period_days"],
                fields["safety_buffer_days"], fields["near_expiry_window_days"],
                fields["purchase_budget"],
            ], col={"xs": 12, "sm": 6, "lg": 4}),
            flow_row([
                policy_fields["forecast_baseline_method"], policy_fields["safety_policy"],
                policy_fields["service_level"],
            ], col={"xs": 12, "sm": 6, "lg": 4}),
            ft.Text(t("note.preferences"),
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY),
            ft.Button(content=t("action.save_settings"), icon=ft.Icons.SAVE_OUTLINED, on_click=save),
        ]),
    )

    backups = app.backup_service.list_backups()
    backup_rows = [
        ft.DataRow(cells=[
            text_cell(path.name),
            text_cell(f"{path.stat().st_size / 1024:.0f} KB", color=T.TEXT_SECONDARY),
            action_cell(lambda e, p=path: _restore(page, navigate, p), icon=ft.Icons.RESTORE, tooltip=t("action.restore")),
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
        t("panel.backups"),
        ft.Column(spacing=T.GAP, controls=[
            ft.Button(content=t("action.backup_now"), icon=ft.Icons.CLOUD_UPLOAD_OUTLINED, on_click=backup_now),
            styled_table(["Backup file", "Size", ""], backup_rows, empty_message=t("empty.no_backups")),
        ]),
        subtitle=f"Saved to {Config.BACKUP_DIR}",
    )

    model = app.forecast_service.model_status()

    def train_model(e) -> None:
        try:
            summary = app.forecast_service.train_model()
            notify(page, f"Trained {summary['version']} \u00b7 adopted={summary.get('adopted')}", "success")
            navigate("/settings")
        except Exception as exc:  # pragma: no cover - training errors
            notify_error(page, exc)

    def reset_model(e) -> None:
        try:
            app.model_service.reset()
            notify(page, t("toast.model_removed"), "success")
            navigate("/settings")
        except Exception as exc:  # pragma: no cover - filesystem
            notify_error(page, exc)

    model_metrics = model.get("metrics") or {}
    wape = model_metrics.get("wape")
    model_panel = section(
        t("panel.forecast_model"),
        ft.Column(spacing=T.GAP_SMALL, controls=[
            _kv("Status", "Adopted" if model.get("adopted") else
                ("Candidate (not adopted)" if model.get("artifact_present") else "No trained model")),
            _kv("Version", model.get("version") or "\u2014"),
            _kv("Holdout WAPE", f"{wape:.1%}" if isinstance(wape, (int, float)) else "\u2014"),
            _kv("Model folder", model.get("model_dir") or str(Config.MODEL_DIR)),
            ft.Text(t("note.forecast_fallback") + " "
                    "missing, worse than the baseline, or incompatible.",
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY),
            ft.Row(spacing=T.GAP_SMALL, controls=[
                ft.Button(content=t("action.train_model"), icon=ft.Icons.MODEL_TRAINING, on_click=train_model),
                ft.OutlinedButton(content=t("action.remove_model"), icon=ft.Icons.DELETE_OUTLINE, on_click=reset_model),
            ]),
        ]),
        subtitle=t("note.model_local"),
        expand=True,
    )

    movement_count = app.db.query_one("SELECT COUNT(*) AS n FROM stock_movements")["n"]
    sales_count = app.db.query_one("SELECT COUNT(*) AS n FROM sales")["n"]
    diagnostics_panel = section(
        t("panel.diagnostics"),
        ft.Column(spacing=T.GAP_SMALL, controls=[
            _kv("Database file", str(Config.DB_PATH)),
            _kv("Schema version", f"{get_schema_version(app.db)} (expected {SCHEMA_VERSION})"),
            _kv("Environment", Config.ENV),
            _kv("Active products", str(app.product_service.count_active())),
            _kv("Stock movements", str(movement_count)),
            _kv("Sales recorded", str(sales_count)),
            _kv("TinyFish configured", "Yes" if Config.TINYFISH_API_KEY else "No (optional)"),
        ]),
        expand=True,
    )

    return scroll_column([
        page_header(t("nav.settings"), t("dashboard.settings_subtitle")),
        store_panel,
        panel_grid([(model_panel, 6), (diagnostics_panel, 6)]),
        backup_panel,
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
            notify(page, t("toast.db_restored"), "success")
            navigate("/settings")
        except Exception as exc:  # pragma: no cover
            notify_error(page, exc)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("action.restore_db")),
        content=ft.Text(
            f"Replace the current database with '{path.name}'? "
            "Unsaved changes since that backup will be lost."
        ),
        actions=[
            ft.TextButton(content=t("action.cancel"), on_click=lambda e: page.pop_dialog()),
            ft.Button(content=t("action.restore"), on_click=do_restore),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
