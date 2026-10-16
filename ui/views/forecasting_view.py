"""StockWise — Forecasting view.

Generate and review a per-product demand forecast, see the recent history, the
accuracy of each baseline on a chronological holdout, and an honest note when
there is not enough data. No SQL or ML math happens here — only service calls.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.theme import StockWiseTheme as T
from domain.exceptions import StockWiseError
from ml.evaluate import format_wape
from ui.components.chart import bar_chart, chart_legend
from ui.components.empty_state import empty_state
from ui.components.feedback import banner, notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.kpi_card import kpi_card
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import styled_table, text_cell

_METHODS = [
    ("auto", "Automatic (best available)"),
    ("seasonal_naive", "Seasonal naive"),
    ("moving_average", "7-day moving average"),
    ("mean", "Average demand"),
    ("xgboost", "XGBoost model (candidate)"),
]

_BASELINE_LABELS = {
    "seasonal_naive": "Seasonal naive (same weekday last week)",
    "moving_average": "7-day moving average",
    "mean": "Average demand",
}


def _day_label(iso: str) -> str:
    return iso[8:10] if len(iso) >= 10 else iso


def build_forecasting_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    products = list(app.product_service.list_products(active_only=True))

    if not products:
        return scroll_column([
            page_header("Forecasting", "Generate and review demand forecasts"),
            ft.Container(
                expand=True,
                bgcolor=T.BG_CARD,
                border_radius=T.RADIUS,
                border=ft.Border.all(1, T.BORDER_SUBTLE),
                content=empty_state(
                    "No products yet",
                    "Add products and record some sales, then come back to forecast demand.",
                    icon=ft.Icons.INSIGHTS_OUTLINED,
                ),
            ),
        ])

    state = {"product_id": products[0].id}

    kpi_row = ft.Row(spacing=T.GAP)
    note_holder = ft.Column(spacing=T.GAP_SMALL)
    chart_holder = ft.Column(spacing=T.GAP_SMALL)
    metrics_holder = ft.Column(spacing=0)
    model_holder = ft.Column(spacing=T.GAP_SMALL)
    table_holder = ft.Column(spacing=0)
    method_text = ft.Text("", size=T.FONT_TINY, color=T.TEXT_TERTIARY)

    horizon_field = text_field(
        "Horizon (days)",
        value=str(Config.DEFAULT_FORECAST_HORIZON),
        width=150,
    )
    method_dd = dropdown_field("Method", _METHODS, value="auto", width=260)

    def _horizon() -> int:
        try:
            return max(1, min(60, int(float((horizon_field.value or "").strip()))))
        except (TypeError, ValueError):
            return Config.DEFAULT_FORECAST_HORIZON

    def render_model() -> None:
        status = app.forecast_service.model_status()
        controls: list[ft.Control] = []
        if not status.get("artifact_present"):
            controls.append(banner(
                "No trained model yet \u2014 forecasts use a transparent baseline. "
                "Train a model to compare it honestly on holdout data.",
                "info",
            ))
            model_holder.controls = controls
            return

        adopted = bool(status.get("adopted"))
        controls.append(banner(
            "XGBoost model adopted and in use."
            if adopted
            else "Model trained but not adopted \u2014 the baseline performed better on holdout.",
            "success" if adopted else "warning",
        ))

        rows: list[ft.DataRow] = []
        model_metrics = status.get("metrics") or {}
        if model_metrics:
            rows.append(ft.DataRow(cells=[
                text_cell("XGBoost", color=T.ACCENT),
                text_cell(f"{model_metrics.get('mae', 0):.2f}"),
                text_cell(format_wape(model_metrics.get("wape"))),
                text_cell(f"{model_metrics.get('bias', 0):+.2f}", color=T.TEXT_SECONDARY),
                text_cell(str(model_metrics.get("n", 0)), color=T.TEXT_SECONDARY),
            ]))
        for name, m in (status.get("baseline_metrics") or {}).items():
            rows.append(ft.DataRow(cells=[
                text_cell(_BASELINE_LABELS.get(name, name)),
                text_cell(f"{m.get('mae', 0):.2f}"),
                text_cell(format_wape(m.get("wape"))),
                text_cell(f"{m.get('bias', 0):+.2f}", color=T.TEXT_SECONDARY),
                text_cell(str(m.get("n", 0)), color=T.TEXT_SECONDARY),
            ]))
        controls.append(styled_table(["Model", "MAE (units)", "WAPE", "Bias", "Days tested"], rows))
        if status.get("trained_at"):
            controls.append(ft.Text(
                f"Trained {status['trained_at']} \u00b7 {status.get('version') or ''} \u00b7 {status.get('notes', '')}",
                size=T.FONT_TINY, color=T.TEXT_TERTIARY,
            ))
        model_holder.controls = controls

    def train_model(e) -> None:
        notify(page, "Training model\u2026 this can take a few seconds.", "info")
        try:
            summary = app.forecast_service.train_model(horizon=_horizon())
        except (StockWiseError, ValueError) as exc:
            notify_error(page, exc)
            return
        notify(
            page,
            "Model trained and adopted." if summary.get("adopted")
            else "Model trained but not adopted \u2014 baseline is better.",
            "success" if summary.get("adopted") else "warning",
        )
        render_model()
        page.update()

    def load(*, regenerate: bool) -> None:
        pid = state["product_id"]
        try:
            horizon = _horizon()
            result = None
            if not regenerate:
                result = app.forecast_service.latest(pid)
                if result is not None and len(result.points) < horizon:
                    result = None
            if result is None:
                result = app.forecast_service.generate(
                    pid, horizon=horizon, method=method_dd.value or "auto"
                )
        except (StockWiseError, ValueError) as exc:
            notify_error(page, exc)
            return

        method_text.value = (
            f"{result.method_label} \u00b7 {result.observed_days} day(s) of history "
            f"\u00b7 horizon {result.horizon} days"
        )

        # --- KPI cards ---
        kpi_row.controls = [
            kpi_card("Average daily demand", f"{result.average_daily_demand:g}",
                     subtitle="units/day (last 28 days)", icon=ft.Icons.TIMELINE),
            kpi_card(f"Forecast \u00b7 next {len(result.points)} days", f"{result.total_qty:g}",
                     subtitle="units expected", icon=ft.Icons.STACKED_LINE_CHART,
                     accent=T.ACCENT),
            kpi_card("Observed sales days", str(result.observed_days),
                     subtitle=f"minimum {Config.MIN_TRAINING_DAYS} for a model",
                     icon=ft.Icons.CALENDAR_MONTH_OUTLINED),
            kpi_card("Method", "Baseline" if result.is_baseline else "XGBoost",
                     subtitle=result.method_label, icon=ft.Icons.MODEL_TRAINING_OUTLINED,
                     accent=T.STATUS_INFO if result.is_baseline else T.STATUS_HEALTHY),
        ]

        # --- Notes ---
        notes: list[ft.Control] = []
        if result.insufficient_data:
            notes.append(banner(result.note or "Insufficient history for a reliable forecast.",
                                "warning"))
        elif result.is_baseline:
            notes.append(banner(
                "Transparent baseline forecast. A trained model is used automatically once "
                "it beats the baseline on holdout data.", "info",
            ))
        note_holder.controls = notes

        # --- Chart: recent history + forecast ---
        series = app.forecast_service.demand_series(pid)
        history = series[-21:]
        hist_vals = [p.quantity for p in history]
        fc_vals = [p.predicted_qty for p in result.points]
        labels = [_day_label(p.date) for p in history] + [_day_label(p.target_date) for p in result.points]
        chart_holder.controls = [
            chart_legend([("History", T.PRIMARY), ("Forecast", T.ACCENT)]),
            bar_chart(hist_vals + fc_vals, labels, forecast_from=len(hist_vals)),
        ]

        # --- Baseline accuracy (chronological holdout) ---
        backtests = app.forecast_service.backtest(pid, horizon=horizon)
        rows = [
            ft.DataRow(cells=[
                text_cell(m.label),
                text_cell(f"{m.mae:.2f}"),
                text_cell(format_wape(m.wape)),
                text_cell(f"{m.bias:+.2f}", color=T.TEXT_SECONDARY),
                text_cell(str(m.n), color=T.TEXT_SECONDARY),
            ])
            for m in backtests
        ]
        metrics_holder.controls = [
            styled_table(
                ["Method", "MAE (units)", "WAPE", "Bias", "Days tested"],
                rows,
                empty_message="Not enough history to back-test yet.",
            )
        ]

        # --- Forecast table ---
        forecast_rows = [
            ft.DataRow(cells=[
                text_cell(p.target_date),
                text_cell(f"{p.predicted_qty:g}"),
            ])
            for p in result.points
        ]
        table_holder.controls = [styled_table(["Date", "Predicted units"], forecast_rows)]

        render_model()
        page.update()

    product_dd = dropdown_field(
        "Product",
        [(str(p.id), f"{p.name} ({p.sku})") for p in products],
        value=str(products[0].id),
        width=360,
        on_select=lambda e: (state.update(product_id=int(e.control.value)), load(regenerate=False)),
    )

    header = page_header(
        "Forecasting",
        "7-day demand forecast with transparent baseline accuracy",
        actions=[
            ft.OutlinedButton(
                content="Rebuild", icon=ft.Icons.REFRESH,
                on_click=lambda e: load(regenerate=True),
            ),
            ft.Button(
                content="Generate forecast", icon=ft.Icons.INSIGHTS,
                on_click=lambda e: load(regenerate=True),
            ),
        ],
    )

    controls_row = ft.Row(
        spacing=T.GAP,
        controls=[product_dd, horizon_field, method_dd, ft.Container(expand=True)],
        vertical_alignment=ft.CrossAxisAlignment.END,
    )

    load(regenerate=False)

    return scroll_column([
        header,
        controls_row,
        note_holder,
        kpi_row,
        section("Demand history and forecast", chart_holder,
                subtitle=None),
        method_text,
        section("Baseline accuracy (chronological holdout)", metrics_holder),
        section(
            "Model",
            model_holder,
            subtitle="XGBoost is adopted only when it beats the baseline on holdout data",
            actions=[ft.OutlinedButton(content="Train model", icon=ft.Icons.MODEL_TRAINING,
                                       on_click=train_model)],
        ),
        section("Forecast detail", table_holder),
    ])
