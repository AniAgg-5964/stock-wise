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
from app.i18n import method_label, t
from domain.exceptions import StockWiseError
from ml.evaluate import format_wape
from ui.components.chart import bar_chart, chart_legend
from ui.components.empty_state import empty_state
from ui.components.feedback import banner, notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.kpi_card import KpiMetric, kpi_strip
from ui.components.layout import flow_row, page_header, scroll_column, section
from ui.components.table import styled_table, text_cell

def _methods() -> list[tuple[str, str]]:
    """Built per call: ``t()`` at import time would freeze the import-time
    language, so a language switch would not reach this dropdown."""
    return [
        ("auto", t("method.auto")),
        ("best", t("method.best")),
        ("seasonal_naive", t("method.seasonal_naive")),
        ("moving_average", t("method.moving_average")),
        ("mean", t("method.mean")),
        ("xgboost", t("method.xgboost")),
    ]


def _day_label(iso: str) -> str:
    return iso[8:10] if len(iso) >= 10 else iso


def build_forecasting_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    products = list(app.product_service.list_products(active_only=True))

    if not products:
        return scroll_column([
            page_header(t("nav.forecasting"), t("dashboard.forecast_subtitle")),
            ft.Container(
                expand=True,
                bgcolor=T.BG_CARD,
                border_radius=T.RADIUS,
                border=ft.Border.all(1, T.BORDER_SUBTLE),
                content=empty_state(
                    t("empty.no_products"),
                    "Add products and record some sales, then come back to forecast demand.",
                    icon=ft.Icons.INSIGHTS_OUTLINED,
                ),
            ),
        ])

    state = {"product_id": products[0].id}

    kpi_holder = ft.Column(spacing=0)
    note_holder = ft.Column(spacing=T.GAP_SMALL)
    chart_holder = ft.Column(spacing=T.GAP_SMALL)
    metrics_holder = ft.Column(spacing=0)
    model_holder = ft.Column(spacing=T.GAP_SMALL)
    table_holder = ft.Column(spacing=0)
    method_text = ft.Text("", size=T.FONT_TINY, color=T.TEXT_TERTIARY)

    horizon_field = text_field(
        t("field.horizon"),
        value=str(Config.DEFAULT_FORECAST_HORIZON),
        width=150,
    )
    method_dd = dropdown_field(t("field.method"), _methods(), value="auto", width=260)

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
            t("toast.model_adopted")
            if adopted
            else "Model trained but not adopted \u2014 the baseline performed better on holdout.",
            "success" if adopted else "warning",
        ))

        rows: list[ft.DataRow] = []
        model_metrics = status.get("metrics") or {}
        if model_metrics:
            rows.append(ft.DataRow(cells=[
                text_cell(t("status.model"), color=T.ACCENT),
                text_cell(f"{model_metrics.get('mae', 0):.2f}"),
                text_cell(format_wape(model_metrics.get("wape"))),
                text_cell(f"{model_metrics.get('bias', 0):+.2f}", color=T.TEXT_SECONDARY),
                text_cell(str(model_metrics.get("n", 0)), color=T.TEXT_SECONDARY),
            ]))
        for name, m in (status.get("baseline_metrics") or {}).items():
            rows.append(ft.DataRow(cells=[
                text_cell(method_label(name)),
                text_cell(f"{m.get('mae', 0):.2f}"),
                text_cell(format_wape(m.get("wape"))),
                text_cell(f"{m.get('bias', 0):+.2f}", color=T.TEXT_SECONDARY),
                text_cell(str(m.get("n", 0)), color=T.TEXT_SECONDARY),
            ]))
        controls.append(styled_table([t("panel.model"), t("col.mae_units"), t("col.wape"), t("col.bias"), t("col.days_tested")], rows))
        if status.get("trained_at"):
            controls.append(ft.Text(
                t("model.trained_on", when=status["trained_at"], model=status.get("version") or "",
                  notes=status.get("notes", "")),
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
            t("toast.model_trained") if summary.get("adopted")
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

        method_text.value = t("model.summary", method=method_label(result.method_label),
                                days=result.observed_days, horizon=result.horizon)

        # --- KPI cards ---
        kpi_holder.controls = [
            kpi_strip([
                KpiMetric(t("metric.avg_daily_demand"), f"{result.average_daily_demand:.1f}",
                          caption=t("cap.units_day"), icon=ft.Icons.TIMELINE),
                KpiMetric(t("metric.forecast_next", days=len(result.points)), f"{result.total_qty:.0f}",
                          caption=t("cap.units_expected"), icon=ft.Icons.STACKED_LINE_CHART,
                          accent=T.ACCENT),
                KpiMetric(t("metric.observed_days"), str(result.observed_days),
                          caption=t("cap.minimum_days", days=Config.MIN_TRAINING_DAYS),
                          icon=ft.Icons.CALENDAR_MONTH_OUTLINED),
                KpiMetric(t("metric.method"),
                          t("status.baseline") if result.is_baseline else t("status.model"),
                          caption=method_label(result.method_label), icon=ft.Icons.MODEL_TRAINING_OUTLINED,
                          accent=T.STATUS_INFO if result.is_baseline else T.STATUS_HEALTHY),
            ])
        ]

        # --- Notes ---
        notes: list[ft.Control] = []
        if result.insufficient_data:
            notes.append(banner(result.note or t("forecast.insufficient_history"),
                                "warning"))
        elif result.is_baseline:
            notes.append(banner(
                # ``result.note`` is domain text written at generation time, so it
                # stays English; the app's own fallback must not.
                result.note or t("forecast.baseline_note"),
                "info",
            ))
        note_holder.controls = notes

        # --- Chart: recent history + forecast ---
        series = app.forecast_service.demand_series(pid)
        history = series[-21:]
        hist_vals = [p.quantity for p in history]
        # Stored forecasts are anchored to the day they were generated, so on a
        # later viewing day their window overlaps the observed history and the
        # x-axis prints duplicate dates. Show only the days not yet observed.
        last_observed = history[-1].date if history else None
        points = [p for p in result.points
                  if last_observed is None or p.target_date > last_observed]
        fc_vals = [p.predicted_qty for p in points]
        labels = [_day_label(p.date) for p in history] + [_day_label(p.target_date) for p in points]
        chart_holder.controls = [
            chart_legend([(t("chart.history"), T.PRIMARY), (t("chart.forecast"), T.ACCENT)]),
            bar_chart(hist_vals + fc_vals, labels, forecast_from=len(hist_vals)),
        ]

        # --- Baseline accuracy (chronological holdout) ---
        backtests = app.forecast_service.backtest(pid, horizon=horizon)
        rows = [
            ft.DataRow(cells=[
                text_cell(method_label(m.label)),
                text_cell(f"{m.mae:.2f}"),
                text_cell(format_wape(m.wape)),
                text_cell(f"{m.bias:+.2f}", color=T.TEXT_SECONDARY),
                text_cell(str(m.n), color=T.TEXT_SECONDARY),
            ])
            for m in backtests
        ]
        metrics_holder.controls = [
            styled_table(
                [t("field.method"), t("col.mae_units"), t("col.wape"), t("col.bias"), t("col.days_tested")],
                rows,
                empty_message=t("empty.no_history"),
            )
        ]

        # --- Forecast table ---
        has_bounds = any(p.lower_bound is not None for p in result.points)
        range_header = (
            t("forecast.range_header", level=result.interval_level)
            if has_bounds and result.interval_level
            else "Likely range"
        )
        forecast_rows = []
        for p in result.points:
            cells = [text_cell(p.target_date), text_cell(f"{p.predicted_qty:g}")]
            if has_bounds:
                cells.append(text_cell(
                    f"{p.lower_bound:g} \u2013 {p.upper_bound:g}"
                    if p.lower_bound is not None else "\u2014",
                    color=T.TEXT_SECONDARY,
                ))
            forecast_rows.append(ft.DataRow(cells=cells))
        headers = [t("col.date"), t("col.predicted_units")] + ([range_header] if has_bounds else [])
        table_holder.controls = [styled_table(headers, forecast_rows)]
        if has_bounds:
            notes.append(ft.Text(
                "The range is the forecast \u00b1 the estimated uncertainty, widening with the "
                "horizon. It is used for the statistical safety-stock policy.",
                size=T.FONT_TINY, color=T.TEXT_TERTIARY,
            ))
            note_holder.controls = notes

        render_model()
        page.update()

    product_dd = dropdown_field(
        t("col.product"),
        [(str(p.id), f"{p.name} ({p.sku})") for p in products],
        value=str(products[0].id),
        width=360,
        on_select=lambda e: (state.update(product_id=int(e.control.value)), load(regenerate=False)),
    )

    header = page_header(
        t("nav.forecasting"),
        t("dashboard.forecast_subtitle2"),
        actions=[
            ft.OutlinedButton(
                content=t("action.rebuild"), icon=ft.Icons.REFRESH,
                on_click=lambda e: load(regenerate=True),
            ),
            ft.Button(
                content=t("action.generate_forecast"), icon=ft.Icons.INSIGHTS,
                on_click=lambda e: load(regenerate=True),
            ),
        ],
    )

    controls_row = flow_row([
        (product_dd, {"xs": 12, "sm": 6, "lg": 5}),
        (horizon_field, {"xs": 12, "sm": 6, "lg": 2}),
        (method_dd, {"xs": 12, "sm": 6, "lg": 4}),
    ])

    load(regenerate=False)

    return scroll_column([
        header,
        controls_row,
        note_holder,
        kpi_holder,
        section(t("panel.demand_forecast"), chart_holder,
                subtitle=None),
        method_text,
        section(t("panel.baseline_accuracy"), metrics_holder),
        section(
            t("panel.model"),
            model_holder,
            subtitle=t("panel.model_note"),
            actions=[ft.OutlinedButton(content=t("action.train_model"), icon=ft.Icons.MODEL_TRAINING,
                                       on_click=train_model)],
        ),
        section(t("panel.forecast_detail"), table_holder),
    ])
