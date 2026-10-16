"""StockWise — Dashboard view.

Every number here is derived from real data. Alerts come from ``AlertsService``
(low stock, near expiry, estimated expiry risk, demand spikes). The forecast
panels show real predictions once forecasts exist; otherwise they say so.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from domain.money import format_money
from ui.components.chart import bar_chart, chart_legend
from ui.components.empty_state import empty_state
from ui.components.kpi_card import kpi_card
from ui.components.layout import page_header, scroll_column, section
from ui.components.status_chip import status_chip
from ui.components.table import styled_table, text_cell

_MOVEMENT_LABELS = {
    "opening_stock": "Opening stock",
    "purchase_receipt": "Receipt",
    "sale": "Sale",
    "return": "Return",
    "waste": "Waste",
    "adjustment": "Adjustment",
    "correction": "Correction",
}

_ALERT_STATUS = {"critical": "critical", "warning": "near_expiry", "info": "info"}


def build_dashboard_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    stats = app.dashboard_service.stats()

    header = page_header(
        "Dashboard",
        "Today's stock position across your store",
        actions=[ft.OutlinedButton(content="Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: navigate("/"))],
    )

    kpis = ft.Row(
        spacing=T.GAP,
        controls=[
            kpi_card("Active Products", str(stats.total_products), icon=ft.Icons.INVENTORY_2_OUTLINED,
                     subtitle="In the catalogue", on_click=lambda e: navigate("/inventory")),
            kpi_card("Stock Value", format_money(stats.total_stock_value), icon=ft.Icons.PAYMENTS_OUTLINED,
                     accent=T.STATUS_HEALTHY, subtitle="At cost", on_click=lambda e: navigate("/inventory")),
            kpi_card("Low / Out of Stock", f"{stats.low_stock_count} / {stats.out_of_stock_count}",
                     icon=ft.Icons.WARNING_AMBER_OUTLINED, accent=T.STATUS_WARNING,
                     subtitle="At or below reorder point", on_click=lambda e: navigate("/inventory")),
            kpi_card("Near / Expired", f"{stats.near_expiry_count} / {stats.expired_batch_count}",
                     icon=ft.Icons.EVENT_BUSY_OUTLINED, accent=T.STATUS_CRITICAL,
                     subtitle="Batches needing attention", on_click=lambda e: navigate("/expiry")),
            kpi_card("Sales Today", format_money(stats.sales_today_total), icon=ft.Icons.POINT_OF_SALE_OUTLINED,
                     accent=T.STATUS_INFO, subtitle="Recorded today", on_click=lambda e: navigate("/sales")),
        ],
    )

    alerts = _alerts_panel(app.alert_service.build(), navigate)
    activity = _activity_panel(stats)

    return scroll_column([
        header,
        kpis,
        ft.Row(spacing=T.GAP, controls=[alerts, activity], vertical_alignment=ft.CrossAxisAlignment.START),
        ft.Row(spacing=T.GAP, controls=[_sales_vs_forecast_panel(app), _top_products_panel(app)],
               vertical_alignment=ft.CrossAxisAlignment.START),
        _quick_actions(navigate),
    ])


def _alerts_panel(alerts, navigate: Callable[[str], None]) -> ft.Control:
    rows: list[ft.Control] = []
    for alert in alerts:
        rows.append(
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                border_radius=T.RADIUS_SMALL,
                ink=True,
                on_click=lambda e, r=alert.route: navigate(r),
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(spacing=1, expand=True, controls=[
                            ft.Text(alert.title, size=T.FONT_BODY, color=T.TEXT_PRIMARY),
                            ft.Text(alert.message, size=T.FONT_TINY, color=T.TEXT_TERTIARY),
                        ]),
                        status_chip(alert.severity.title(), _ALERT_STATUS.get(alert.severity, "info")),
                    ],
                ),
            )
        )

    content = (
        ft.Column(spacing=T.GAP_SMALL, controls=rows)
        if rows
        else empty_state("Nothing needs attention", "No low-stock, expiring or rising-demand items right now.",
                         icon=ft.Icons.CHECK_CIRCLE_OUTLINE)
    )
    return section(
        "Alerts", content, subtitle="Low stock, expiry risk and demand spikes", expand=True,
        actions=[ft.TextButton(content="View expiry", on_click=lambda e: navigate("/expiry"))] if rows else None,
    )


def _activity_panel(stats) -> ft.Control:
    rows: list[ft.Control] = []
    for product, movement in stats.recent_movements:
        delta = movement.quantity_delta
        color = T.STATUS_HEALTHY if delta >= 0 else T.STATUS_CRITICAL
        rows.append(
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(spacing=1, expand=True, controls=[
                        ft.Text(product.name, size=T.FONT_BODY, color=T.TEXT_PRIMARY),
                        ft.Text(
                            f"{_MOVEMENT_LABELS.get(movement.movement_type, movement.movement_type)} "
                            f"\u00b7 {movement.occurred_at}",
                            size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                        ),
                    ]),
                    ft.Text(f"{delta:+g}", size=T.FONT_BODY, color=color, weight=ft.FontWeight.W_600),
                ],
            )
        )

    content = (
        ft.Column(spacing=T.GAP_SMALL, controls=rows)
        if rows
        else empty_state("No stock movements yet", "Receipts, sales and adjustments appear here.",
                         icon=ft.Icons.SWAP_VERT)
    )
    return section("Recent Stock Activity", content, subtitle="Latest ledger entries", expand=True)


def _sales_vs_forecast_panel(app) -> ft.Control:
    today = date.today()
    start = (today - timedelta(days=13)).isoformat()
    history = app.forecast_repo.total_demand_by_date(start, today.isoformat())
    hist_values = [q for _, q in history]
    hist_labels = [d[8:10] for d, _ in history]

    # Aggregate the next 7 days of stored forecasts across products.
    by_date: dict[str, float] = {}
    for product in app.product_service.list_products(active_only=True):
        latest = app.forecast_service.latest(product.id)
        if latest is None:
            continue
        for point in latest.points[:7]:
            by_date[point.target_date] = by_date.get(point.target_date, 0.0) + point.predicted_qty

    fc_dates = sorted(by_date)[:7]
    fc_values = [by_date[d] for d in fc_dates]
    fc_labels = [d[8:10] for d in fc_dates]

    if not fc_values:
        return section(
            "Sales vs Forecast",
            empty_state("No forecasts yet",
                        "Generate a forecast to see predicted demand against recent sales.",
                        icon=ft.Icons.INSIGHTS_OUTLINED),
            subtitle="Units per day \u00b7 last 14 days and next 7", expand=True,
        )

    chart = ft.Column(spacing=T.GAP_SMALL, controls=[
        chart_legend([("Recent sales", T.PRIMARY), ("Forecast", T.ACCENT)]),
        bar_chart(hist_values + fc_values, hist_labels + fc_labels, forecast_from=len(hist_values)),
    ])
    return section("Sales vs Forecast", chart, subtitle="Units per day \u00b7 last 14 days and next 7", expand=True)


def _top_products_panel(app) -> ft.Control:
    ranked: list[tuple[str, float, float]] = []
    for product in app.product_service.list_products(active_only=True):
        latest = app.forecast_service.latest(product.id)
        if latest is None or not latest.points:
            continue
        total = sum(p.predicted_qty for p in latest.points[:7])
        ranked.append((product.name, total, latest.average_daily_demand))
    ranked.sort(key=lambda r: -r[1])

    rows = [
        ft.DataRow(cells=[
            text_cell(str(i + 1), color=T.TEXT_TERTIARY),
            text_cell(name),
            text_cell(f"{total:g}"),
            text_cell(f"{avg:g}", color=T.TEXT_SECONDARY),
        ])
        for i, (name, total, avg) in enumerate(ranked[:6])
    ]
    content = styled_table(["#", "Product", "Forecast 7d", "Avg/day"], rows,
                          empty_message="Generate forecasts to populate this list.")
    return section("Top Products by Predicted Demand", content, subtitle="Next 7 days", expand=True)


def _quick_actions(navigate: Callable[[str], None]) -> ft.Control:
    return section(
        "Quick Actions",
        ft.Row(
            spacing=T.GAP_SMALL,
            controls=[
                ft.Button(content="Record Sale", icon=ft.Icons.ADD_SHOPPING_CART, on_click=lambda e: navigate("/sales")),
                ft.OutlinedButton(content="Add Product", icon=ft.Icons.ADD, on_click=lambda e: navigate("/inventory")),
                ft.OutlinedButton(content="Generate Forecast", icon=ft.Icons.AUTO_GRAPH,
                                  on_click=lambda e: navigate("/forecasting")),
                ft.OutlinedButton(content="Review Reorders", icon=ft.Icons.SHOPPING_CART_CHECKOUT,
                                  on_click=lambda e: navigate("/reorder")),
            ],
        ),
    )
