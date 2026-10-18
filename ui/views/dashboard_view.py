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
from app.config import Config
from app.theme import StockWiseTheme as T
from domain.money import format_money
from ui.components.chart import area_chart, chart_legend
from ui.components.empty_state import empty_state
from ui.components.kpi_card import kpi_card
from ui.components.layout import (
    KPI_COL,
    icon_tile,
    kpi_grid,
    list_row,
    page_header,
    panel_grid,
    scroll_column,
    section,
)
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

_STATUS_LABELS = {
    "healthy": "In stock",
    "low": "Low stock",
    "out_of_stock": "Out of stock",
    "near_expiry": "Near expiry",
    "expired": "Expired",
    "at_risk": "At risk",
}


def build_dashboard_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context

    # Read the product list, inventory snapshot and stored forecasts ONCE and share
    # them across the panels. Each was previously rebuilt per panel, which is what
    # made this screen take seconds to render.
    products = list(app.product_service.list_products(active_only=True))
    snapshots = list(app.inventory_service.snapshots_for_products(products))
    forecasts = app.forecast_service.latest_for_products([p.id for p in products])
    stats = app.dashboard_service.stats(products=products, snapshots=snapshots)

    today = date.today()
    range_label = f"{(today - timedelta(days=13)).strftime('%d %b')} \u2013 {today.strftime('%d %b, %Y')}"
    header = page_header(
        "Dashboard",
        "Overview of your inventory, sales and forecast at a glance.",
        actions=[
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                border_radius=T.RADIUS_SMALL,
                bgcolor=T.BG_CARD,
                border=ft.Border.all(1, T.BORDER),
                content=ft.Row(spacing=8, tight=True, controls=[
                    ft.Icon(ft.Icons.CALENDAR_MONTH_OUTLINED, size=15, color=T.TEXT_SECONDARY),
                    ft.Text(range_label, size=T.FONT_SMALL, color=T.TEXT_SECONDARY),
                ]),
            ),
            ft.OutlinedButton(content="Refresh", icon=ft.Icons.REFRESH,
                              on_click=lambda e: navigate("/")),
        ],
    )

    out_of_stock = stats.out_of_stock_count
    kpis = kpi_grid([
        kpi_card("Total Products", str(stats.total_products), icon=ft.Icons.INVENTORY_2_OUTLINED,
                 accent=T.STATUS_INFO, subtitle="In the catalogue", col=KPI_COL,
                 on_click=lambda e: navigate("/inventory")),
        kpi_card("Total Stock Value", format_money(stats.total_stock_value),
                 icon=ft.Icons.PAYMENTS_OUTLINED, accent=T.STATUS_HEALTHY, col=KPI_COL,
                 subtitle="At cost", on_click=lambda e: navigate("/inventory")),
        kpi_card("Out of Stock", str(out_of_stock), icon=ft.Icons.REMOVE_SHOPPING_CART_OUTLINED,
                 accent=T.STATUS_CRITICAL, col=KPI_COL,
                 subtitle=(f"{stats.low_stock_count} low stock" if stats.low_stock_count
                           else "Requires attention"),
                 delta_kind="down" if out_of_stock else "muted",
                 on_click=lambda e: navigate("/inventory")),
        kpi_card("Expiry Risk", str(stats.near_expiry_count),
                 icon=ft.Icons.EVENT_BUSY_OUTLINED, accent=T.STATUS_WARNING, col=KPI_COL,
                 subtitle=f"Within {Config.NEAR_EXPIRY_WINDOW_DAYS} days",
                 delta_kind="warn" if stats.near_expiry_count else "muted",
                 on_click=lambda e: navigate("/expiry")),
    ])

    return scroll_column([
        header,
        kpis,
        panel_grid([
            (_sales_vs_forecast_panel(forecasts), 7),
            (_top_products_panel(products, snapshots, forecasts), 5),
        ]),
        _quick_actions(navigate),
        panel_grid([
            (_alerts_panel(
                app.alert_service.build(products=products, snapshots=snapshots), navigate,
            ), 6),
            (_activity_panel(stats), 6),
        ]),
    ])


def _alerts_panel(alerts, navigate: Callable[[str], None]) -> ft.Control:
    rows: list[ft.Control] = []
    for alert in alerts[:6]:
        status = _ALERT_STATUS.get(alert.severity, "info")
        rows.append(
            list_row(
                leading=ft.Container(
                    width=8, height=8, border_radius=4,
                    bgcolor=T.status_color(status),
                    margin=ft.Margin.only(top=6),
                ),
                title=alert.title,
                subtitle=alert.message,
                trailing=status_chip(alert.severity.title(), status),
                on_click=lambda e, r=alert.route: navigate(r),
            )
        )

    content = (
        ft.Column(spacing=2, controls=rows)
        if rows
        else empty_state("Nothing needs attention",
                         "No low-stock, expiring or rising-demand items right now.",
                         icon=ft.Icons.CHECK_CIRCLE_OUTLINE)
    )
    return section(
        "Recent Alerts", content, subtitle="Low stock, expiry risk and demand spikes",
        actions=([ft.TextButton(content="View all", on_click=lambda e: navigate("/expiry"))] if rows else None),
    )


def _activity_panel(stats) -> ft.Control:
    rows: list[ft.Control] = []
    for product, movement in stats.recent_movements[:6]:
        delta = movement.quantity_delta
        positive = delta >= 0
        rows.append(
            list_row(
                leading=icon_tile(
                    ft.Icons.ARROW_UPWARD if positive else ft.Icons.ARROW_DOWNWARD,
                    color=T.STATUS_HEALTHY if positive else T.STATUS_CRITICAL,
                    size=32,
                ),
                title=product.name,
                subtitle=f"{_MOVEMENT_LABELS.get(movement.movement_type, movement.movement_type)}"
                         f" \u00b7 {movement.occurred_at}",
                trailing=ft.Text(f"{delta:+g}", size=T.FONT_BODY,
                                 color=T.STATUS_HEALTHY if positive else T.STATUS_CRITICAL,
                                 weight=ft.FontWeight.W_600),
            )
        )

    content = (
        ft.Column(spacing=2, controls=rows)
        if rows
        else empty_state("No stock movements yet", "Receipts, sales and adjustments appear here.",
                         icon=ft.Icons.SWAP_VERT)
    )
    return section("Recent Stock Activity", content, subtitle="Latest ledger entries")


def _sales_vs_forecast_panel(forecasts) -> ft.Control:
    today = date.today()
    start = (today - timedelta(days=13)).isoformat()
    history = app_context.forecast_repo.total_demand_by_date(start, today.isoformat())
    hist_values = [q for _, q in history]
    hist_labels = [_day_label(d) for d, _ in history]

    # Aggregate the next 7 days of stored forecasts across products.
    by_date: dict[str, float] = {}
    upper_by_date: dict[str, float] = {}
    for latest in forecasts.values():
        if latest is None:
            continue
        for point in latest.points[:7]:
            by_date[point.target_date] = by_date.get(point.target_date, 0.0) + point.predicted_qty
            if point.upper_bound is not None:
                upper_by_date[point.target_date] = (
                    upper_by_date.get(point.target_date, 0.0) + point.upper_bound
                )

    fc_dates = sorted(by_date)[:7]
    fc_values = [by_date[d] for d in fc_dates]
    fc_labels = [_day_label(d) for d in fc_dates]
    fc_upper = [upper_by_date.get(d) for d in fc_dates] if len(upper_by_date) == len(fc_dates) else None

    if not fc_values:
        return section(
            "Sales vs Forecast",
            empty_state("No forecasts yet",
                        "Generate a forecast to see predicted demand against recent sales.",
                        icon=ft.Icons.INSIGHTS_OUTLINED),
            subtitle="Units per day \u00b7 last 14 days and next 7",
        )

    legend_items = [("Actual sales", T.PRIMARY), ("Forecast", T.ACCENT)]

    def _render(*, with_band: bool) -> ft.Control:
        return ft.Column(spacing=T.GAP_SMALL, controls=[
            area_chart(
                hist_values + fc_values,
                hist_labels + fc_labels,
                height=210,
                forecast_from=len(hist_values),
                upper=(hist_values + fc_upper) if (with_band and fc_upper) else None,
            ),
        ])

    content = ft.Column(spacing=T.GAP_SMALL, controls=[
        chart_legend(legend_items),
        _render(with_band=bool(fc_upper)),
        ft.Text("The shaded band is the forecast's likely range (widening with the horizon)."
                if fc_upper else "Generate a model forecast to see a confidence band around predictions.",
                size=T.FONT_TINY, color=T.TEXT_TERTIARY),
    ])
    return section("Sales vs Forecast", content, subtitle="Units per day \u00b7 last 14 days and next 7")


def _top_products_panel(products, snapshots, forecasts) -> ft.Control:
    status_by_id = {}
    for snap in snapshots:
        status_by_id[snap.product.id] = snap.status

    ranked: list[tuple[str, float, str]] = []
    for product in products:
        latest = forecasts.get(product.id)
        if latest is None or not latest.points:
            continue
        total = sum(p.predicted_qty for p in latest.points[:7])
        ranked.append((product.name, total, status_by_id.get(product.id, "healthy")))
    ranked.sort(key=lambda r: -r[1])

    rows = [
        ft.DataRow(cells=[
            text_cell(name, weight=ft.FontWeight.W_500),
            text_cell(f"{total:g}", weight=ft.FontWeight.W_600),
            ft.DataCell(status_chip(_STATUS_LABELS.get(status, status), status)),
        ])
        for name, total, status in ranked[:6]
    ]
    content = styled_table(["Product", "Forecast 7d", "Stock status"], rows,
                           empty_message="Generate forecasts to populate this list.")
    return section(
        "Top Products by Predicted Demand", content, subtitle="Next 7 days",
        actions=[ft.TextButton(content="View all", on_click=lambda e: navigate("/forecasting"))]
        if rows else None,
    )


def _quick_actions(navigate: Callable[[str], None]) -> ft.Control:
    def tile(icon: str, title: str, subtitle: str, route: str, accent: str) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(horizontal=14, vertical=12),
            border_radius=T.RADIUS_SMALL,
            bgcolor=T.BG_HOVER,
            border=ft.Border.all(1, T.BORDER_SUBTLE),
            ink=True,
            on_click=lambda e: navigate(route),
            content=ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    icon_tile(icon, color=accent, size=38),
                    ft.Column(spacing=1, expand=True, controls=[
                        ft.Text(title, size=T.FONT_BODY, weight=ft.FontWeight.W_600,
                                color=T.TEXT_PRIMARY),
                        ft.Text(subtitle, size=T.FONT_TINY, color=T.TEXT_TERTIARY),
                    ]),
                ],
            ),
        )

    grid = ft.Column(spacing=T.GAP_SMALL, controls=[
        ft.Row(spacing=T.GAP_SMALL, controls=[
            tile(ft.Icons.ADD_CIRCLE_OUTLINE, "Add Product", "New product to inventory",
                 "/inventory", T.STATUS_INFO),
            tile(ft.Icons.ADD_SHOPPING_CART_OUTLINED, "Record Sale", "Update stock & sales",
                 "/sales", T.ACCENT),
        ]),
        ft.Row(spacing=T.GAP_SMALL, controls=[
            tile(ft.Icons.AUTO_GRAPH_OUTLINED, "Generate Forecast", "Predict demand for the week",
                 "/forecasting", T.STATUS_HEALTHY),
            tile(ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED, "Reorder Suggestions",
                 "Based on demand & stock", "/reorder", T.STATUS_WARNING),
        ]),
    ])
    return section("Quick Actions", grid, subtitle="Jump to the tasks you do most")


def _day_label(iso: str) -> str:
    return iso[8:10] if len(iso) >= 10 else iso
