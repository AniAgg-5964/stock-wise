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
from domain.money import format_money
from ui.components.chart import bar_chart
from ui.components.empty_state import empty_state
from ui.components.feedback import notify, notify_error
from ui.components.kpi_card import kpi_card
from ui.components.layout import page_header, scroll_column, section
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
        "Reports",
        f"Sales, stock, forecasting and purchasing \u00b7 last {_PERIOD} days",
        actions=[ft.OutlinedButton(content="Refresh", icon=ft.Icons.REFRESH,
                                   on_click=lambda e: navigate("/reports"))],
    )

    kpis = ft.Row(
        spacing=T.GAP,
        controls=[
            kpi_card("Revenue", format_money(sales["revenue"]), icon=ft.Icons.CURRENCY_RUPEE,
                     accent=T.STATUS_HEALTHY, subtitle=f"last {_PERIOD} days"),
            kpi_card("Units sold", f"{sales['units']:g}", icon=ft.Icons.INVENTORY_2_OUTLINED,
                     subtitle=f"{sales['orders']} orders"),
            kpi_card("Gross margin", format_money(sales["margin"]), icon=ft.Icons.TRENDING_UP,
                     accent=T.ACCENT, subtitle="price \u2212 cost snapshot"),
            kpi_card("Stock value", format_money(valuation["total_value"]), icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                     subtitle=f"{valuation['total_qty']:g} units on hand"),
            kpi_card("Waste (90d)", f"{waste['total_units']:g} units", icon=ft.Icons.DELETE_OUTLINE,
                     accent=T.STATUS_CRITICAL if waste["total_units"] else T.STATUS_HEALTHY,
                     subtitle="written-off stock"),
        ],
    )

    # ---- sales trend ---------------------------------------------------------
    if by_day:
        chart = bar_chart([float(r["revenue"]) for r in by_day],
                          [str(r["day"])[5:] for r in by_day], height=200)
    else:
        chart = empty_state("No sales in this period", "Record sales to populate this report.",
                            icon=ft.Icons.SHOW_CHART)
    sales_panel = section("Revenue by day", chart, subtitle=f"Last {_PERIOD} days", expand=True)

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
    top_panel = section("Top products", styled_table(["#", "Product", "Units", "Revenue"], top_rows,
                                                     empty_message="No sales yet."),
                        subtitle=f"By revenue \u00b7 last {_PERIOD} days", expand=True)

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
        "Stock valuation", styled_table(["Product", "On hand", "Value", "Expired"], val_rows,
                                        empty_message="No products yet."),
        subtitle=f"Total {format_money(valuation['total_value'])} \u00b7 expired "
                 f"{format_money(valuation['expired_value'])}",
    )

    # ---- forecast accuracy ---------------------------------------------------
    model = accuracy["model"]
    if model.get("available"):
        model_line = ft.Row(spacing=T.GAP_SMALL, controls=[
            ft.Text(f"Model: {model.get('version') or 'n/a'}", size=T.FONT_SMALL, color=T.TEXT_PRIMARY),
            ft.Text("adopted" if model.get("adopted") else "candidate (not adopted)",
                    size=T.FONT_SMALL,
                    color=T.STATUS_HEALTHY if model.get("adopted") else T.STATUS_WARNING,
                    weight=ft.FontWeight.W_600),
        ])
    else:
        model_line = ft.Text("No trained model yet \u2014 baselines only (honest fallback).",
                             size=T.FONT_SMALL, color=T.TEXT_SECONDARY)

    acc_rows = [
        ft.DataRow(cells=[
            text_cell(r["name"]),
            text_cell(r["best_method"]),
            text_cell(f"{r['wape']:.1%}" if r["wape"] is not None else "\u2014"),
            text_cell(f"{r['mae']:.2f}", color=T.TEXT_SECONDARY),
        ])
        for r in accuracy["products"][:12]
    ]
    acc_panel = section(
        "Forecast accuracy",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            model_line,
            styled_table(["Product", "Best method", "WAPE", "MAE"], acc_rows,
                         empty_message="Not enough demand history to backtest yet."),
        ]),
        subtitle="Chronological holdout \u00b7 lower WAPE is better",
    )

    # ---- waste + purchasing --------------------------------------------------
    waste_rows = [ft.DataRow(cells=[text_cell(r["name"]), text_cell(f"{r['qty']:g}")])
                  for r in waste["rows"][:8]]
    waste_panel = section("Waste & shrinkage", styled_table(["Product", "Units"], waste_rows,
                                                            empty_message="No waste recorded \u2014 good."),
                          subtitle=f"Written off in the last {_WASTE_PERIOD} days", expand=True)

    po_rows = [
        ft.DataRow(cells=[
            text_cell(f"#{po['id']}"),
            text_cell(po.get("supplier_name") or "\u2014"),
            text_cell(po.get("status", "").title()),
            text_cell(format_money(po.get("total_amount") or 0)),
        ])
        for po in purchasing["open"][:8]
    ]
    po_panel = section("Open purchase orders",
                       styled_table(["PO", "Supplier", "Status", "Value"], po_rows,
                                    empty_message="No open orders."),
                       subtitle=f"{purchasing['open_count']} open \u00b7 "
                                f"{format_money(purchasing['open_value'])} committed", expand=True)

    # ---- exports -------------------------------------------------------------
    def export(name: str, columns: list[str], rows: list[dict]) -> None:
        try:
            target = reports.export_csv(EXPORT_DIR / name, columns, rows)
            notify(page, f"Saved {target.name}", "success")
        except Exception as exc:  # pragma: no cover - filesystem
            notify_error(page, exc)

    export_panel = section(
        "Export reports (CSV)",
        ft.Row(spacing=T.GAP_SMALL, wrap=True, controls=[
            ft.OutlinedButton(content="Sales by day", icon=ft.Icons.TABLE_VIEW,
                              on_click=lambda e: export(
                                  "report_sales_by_day.csv", ["day", "revenue", "units"],
                                  [{"day": r["day"], "revenue": r["revenue"], "units": r["units"]} for r in by_day])),
            ft.OutlinedButton(content="Top products", icon=ft.Icons.LEADERBOARD,
                              on_click=lambda e: export(
                                  "report_top_products.csv", ["name", "qty", "revenue"], top)),
            ft.OutlinedButton(content="Stock valuation", icon=ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
                              on_click=lambda e: export(
                                  "report_stock_valuation.csv",
                                  ["product_id", "name", "unit", "qty", "value", "expired_qty", "expired_value"],
                                  valuation["rows"])),
            ft.OutlinedButton(content="Forecast accuracy", icon=ft.Icons.INSIGHTS_OUTLINED,
                              on_click=lambda e: export(
                                  "report_forecast_accuracy.csv",
                                  ["product_id", "name", "best_method", "wape", "mae"],
                                  accuracy["products"])),
            ft.OutlinedButton(content="Waste", icon=ft.Icons.DELETE_OUTLINE,
                              on_click=lambda e: export("report_waste.csv", ["name", "qty"], waste["rows"])),
        ]),
        subtitle=f"Files are written to {EXPORT_DIR}",
    )

    return scroll_column([
        header,
        kpis,
        ft.Row(spacing=T.GAP, controls=[sales_panel, top_panel],
               vertical_alignment=ft.CrossAxisAlignment.START),
        val_panel,
        acc_panel,
        ft.Row(spacing=T.GAP, controls=[waste_panel, po_panel],
               vertical_alignment=ft.CrossAxisAlignment.START),
        export_panel,
    ])
