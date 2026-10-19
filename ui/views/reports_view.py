"""StockWise \u2014 Reports view.

Descriptive reporting built entirely from stored data: sales and margin, top
products, stock valuation, waste, forecast accuracy and open purchase orders.
Every panel can be exported to CSV. No report mutates data.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.theme import StockWiseTheme as T
from app.i18n import method_label, t
from domain.money import format_money
from ui.components.chart import bar_chart
from ui.components.empty_state import empty_state
from ui.components.feedback import notify, notify_error
from ui.components.kpi_card import KpiMetric, kpi_strip
from ui.components.layout import card, flow_row, list_row, page_header, panel_grid, scroll_column, section
from ui.components.table import styled_table, text_cell

EXPORT_DIR = Config.APP_DATA_DIR / "exports"
_PERIOD = 30
_WASTE_PERIOD = 90


def build_reports_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    reports = app.report_service

    sales = reports.sales_summary(_PERIOD)
    by_day = reports.sales_by_day(_PERIOD)
    top = reports.top_products(_PERIOD, limit=8)
    valuation = reports.stock_valuation()
    waste = reports.waste_summary(_WASTE_PERIOD)
    accuracy = reports.forecast_accuracy()
    purchasing = reports.purchasing_summary()

    header = page_header(
        t("nav.reports"),
        t("dashboard.reports_subtitle"),
        actions=[ft.OutlinedButton(content=t("action.refresh"), icon=ft.Icons.REFRESH,
                                   on_click=lambda e: navigate("/reports"))],
    )

    kpis = kpi_strip([
        KpiMetric(t("metric.revenue"), format_money(sales["revenue"]), icon=ft.Icons.CURRENCY_RUPEE,
                  accent=T.STATUS_HEALTHY, caption=t("cap.last_period", days=_PERIOD)),
        KpiMetric(t("metric.units_sold"), f"{sales['units']:g}", icon=ft.Icons.INVENTORY_2_OUTLINED,
                  caption=t("cap.orders", count=sales["orders"])),
        KpiMetric(t("metric.gross_margin"), format_money(sales["margin"]), icon=ft.Icons.TRENDING_UP,
                  accent=T.ACCENT, caption=t("cap.price_minus_cost")),
        KpiMetric(t("metric.stock_value"), format_money(valuation["total_value"]),
                  icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                  caption=t("cap.units_on_hand", qty=f"{valuation['total_qty']:g}")),
    ])

    # Waste was a fifth tile, which is what left it orphaned on its own row under
    # a four-wide strip. It reads better as a sentence: "no stock written off" is
    # the result the shop is trying for, not a number to tile.
    waste_units = waste["total_units"]
    waste_note = list_row(
        leading=ft.Container(
            width=8, height=8, border_radius=4,
            bgcolor=T.STATUS_CRITICAL if waste_units else T.STATUS_HEALTHY,
        ),
        title=(t("waste.units", qty=f"{waste_units:g}", days=_WASTE_PERIOD)
               if waste_units else t("waste.none", days=_WASTE_PERIOD)),
        subtitle=t("note.waste_detail"),
    )

    # ---- sales trend ---------------------------------------------------------
    if by_day:
        chart = bar_chart([float(r["revenue"]) for r in by_day],
                          [str(r["day"])[5:] for r in by_day], height=200)
    else:
        chart = empty_state(t("empty.no_sales_period"), "Record sales to populate this report.",
                            icon=ft.Icons.SHOW_CHART)
    sales_panel = section(t("panel.revenue_by_day"), chart, subtitle=t("cap.last_period_cap", days=_PERIOD), expand=True)

    # ---- top products --------------------------------------------------------
    top_rows = [
        ft.DataRow(cells=[
            text_cell(str(i + 1), color=T.TEXT_TERTIARY),
            text_cell(r["name"]),
            text_cell(f"{r['qty']:g}"),
            text_cell(format_money(r["revenue"])),
        ])
        for i, r in enumerate(top)
    ]
    top_panel = section(t("panel.top_products"), styled_table([t("col.rank"), t("col.product"), t("col.units"), t("col.revenue")], top_rows,
                                                     empty_message=t("empty.no_sales")),
                        subtitle=t("cap.by_revenue", days=_PERIOD), expand=True)

    # ---- stock valuation -----------------------------------------------------
    val_rows = [
        ft.DataRow(cells=[
            text_cell(r["name"]),
            text_cell(f"{r['qty']:g} {r['unit']}"),
            text_cell(format_money(r["value"])),
            text_cell(f"{r['expired_qty']:g}" if r["expired_qty"] else "\u2014",
                      color=T.STATUS_CRITICAL if r["expired_qty"] else T.TEXT_TERTIARY),
        ])
        for r in valuation["rows"][:12]
    ]
    val_panel = section(
        t("panel.stock_valuation"), styled_table([t("col.product"), t("col.on_hand"), t("col.value"), t("col.expired")], val_rows,
                                        empty_message=t("empty.no_products_short")),
        subtitle=t("cap.total_expired", total=format_money(valuation["total_value"]),
                   expired=format_money(valuation["expired_value"])),
    )

    # ---- forecast accuracy ---------------------------------------------------
    model = accuracy["model"]
    if model.get("available"):
        model_line = ft.Row(spacing=T.GAP_SMALL, controls=[
            ft.Text(t("cap.model_id", model=model.get("version") or "n/a"),
                    size=T.FONT_SMALL, color=T.TEXT_PRIMARY),
            ft.Text(t("status.adopted") if model.get(t("status.adopted")) else t("status.candidate"),
                    size=T.FONT_SMALL,
                    color=T.STATUS_HEALTHY if model.get(t("status.adopted")) else T.STATUS_WARNING,
                    weight=ft.FontWeight.W_600),
        ])
    else:
        model_line = ft.Text("No trained model yet \u2014 baselines only (honest fallback).",
                             size=T.FONT_SMALL, color=T.TEXT_SECONDARY)

    acc_rows = [
        ft.DataRow(cells=[
            text_cell(r["name"]),
            text_cell(method_label(r["best_method"])),
            text_cell(f"{r['wape']:.1%}" if r["wape"] is not None else "\u2014"),
            text_cell(f"{r['mae']:.2f}", color=T.TEXT_SECONDARY),
        ])
        for r in accuracy["products"][:12]
    ]
    acc_panel = section(
        t("panel.forecast_accuracy"),
        ft.Column(spacing=T.GAP_SMALL, controls=[
            model_line,
            styled_table([t("col.product"), t("col.best_method"), t("col.wape"), t("col.mae")], acc_rows,
                         empty_message=t("empty.no_backtest")),
        ]),
        subtitle=t("note.holdout_lower_better"),
    )

    # ---- waste + purchasing --------------------------------------------------
    waste_rows = [ft.DataRow(cells=[text_cell(r["name"]), text_cell(f"{r['qty']:g}")])
                  for r in waste["rows"][:8]]
    waste_panel = section(t("panel.waste_shrinkage"), styled_table([t("col.product"), t("col.units")], waste_rows,
                                                            empty_message=t("empty.no_waste")),
                          subtitle=t("cap.written_off_window", days=_WASTE_PERIOD), expand=True)

    po_rows = [
        ft.DataRow(cells=[
            text_cell(f"#{po['id']}"),
            text_cell(po.get("supplier_name") or "\u2014"),
            text_cell(po.get("status", "").title()),
            text_cell(format_money(po.get("total_amount") or 0)),
        ])
        for po in purchasing["open"][:8]
    ]
    po_panel = section(t("panel.open_orders"),
                       styled_table([t("col.po"), t("col.supplier_name"), t("field.status"), t("col.value")], po_rows,
                                    empty_message=t("empty.no_orders")),
                       subtitle=t("cap.open_committed", count=purchasing["open_count"],
                                  value=format_money(purchasing["open_value"])), expand=True)

    # ---- exports -------------------------------------------------------------
    def export(name: str, columns: list[str], rows: list[dict]) -> None:
        try:
            target = reports.export_csv(EXPORT_DIR / name, columns, rows)
            notify(page, f"Saved {target.name}", "success")
        except Exception as exc:  # pragma: no cover - filesystem
            notify_error(page, exc)

    export_panel = section(
        t("panel.export_reports"),
        flow_row([
            ft.OutlinedButton(content=t("panel.sales_by_day"), icon=ft.Icons.TABLE_VIEW,
                              on_click=lambda e: export(
                                  "report_sales_by_day.csv", ["day", "revenue", "units"],
                                  [{"day": r["day"], "revenue": r["revenue"], "units": r["units"]} for r in by_day])),
            ft.OutlinedButton(content=t("panel.top_products"), icon=ft.Icons.LEADERBOARD,
                              on_click=lambda e: export(
                                  "report_top_products.csv", ["name", "qty", "revenue"], top)),
            ft.OutlinedButton(content=t("panel.stock_valuation"), icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                              on_click=lambda e: export(
                                  "report_stock_valuation.csv",
                                  ["product_id", "name", "unit", "qty", "value", "expired_qty", "expired_value"],
                                  valuation["rows"])),
            ft.OutlinedButton(content=t("panel.forecast_accuracy"), icon=ft.Icons.INSIGHTS_OUTLINED,
                              on_click=lambda e: export(
                                  "report_forecast_accuracy.csv",
                                  ["product_id", "name", "best_method", "wape", "mae"],
                                  accuracy["products"])),
            ft.OutlinedButton(content=t("panel.waste"), icon=ft.Icons.DELETE_OUTLINE,
                              on_click=lambda e: export("report_waste.csv", ["name", "qty"], waste["rows"])),
        ], col={"xs": 12, "sm": 6, "lg": 4}),
        subtitle=t("exports.location", path=EXPORT_DIR),
    )

    return scroll_column([
        header,
        kpis,
        card(waste_note, padding=ft.Padding.symmetric(horizontal=6, vertical=2)),
        panel_grid([(sales_panel, 6), (top_panel, 6)]),
        val_panel,
        acc_panel,
        panel_grid([(waste_panel, 6), (po_panel, 6)]),
        export_panel,
    ])
