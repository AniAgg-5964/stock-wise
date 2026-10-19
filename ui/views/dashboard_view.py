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
from app.i18n import t
from app.theme import StockWiseTheme as T
from domain.money import format_money
from ui.components.chart import area_chart, chart_legend
from ui.components.empty_state import empty_state
from ui.components.kpi_card import KpiMetric, kpi_strip
from ui.components.layout import (
    icon_tile,
    list_row,
    page_header,
    panel_grid,
    scroll_column,
    section,
)
from ui.components.status_chip import status_chip
from ui.components.table import styled_table, text_cell

# Ledger movement types -> translation keys. Every ``MovementType`` value is
# covered, so the fallback only ever guards against an unknown future type.
_MOVEMENT_LABELS = {
    "opening_stock": "movement.opening_stock",
    "purchase_receipt": "movement.purchase_receipt",
    "sale": "movement.sale",
    "return": "movement.return",
    "waste": "movement.waste",
    "adjustment": "movement.adjustment",
    "correction": "movement.correction",
    "transfer": "movement.transfer",
}

_ALERT_STATUS = {"critical": "critical", "warning": "near_expiry", "info": "info"}

# A ledger entry is coloured by what the movement *means*, not by its sign. The
# old version painted every sale red, which made an ordinary day of trading look
# like an error screen and left red with no meaning of its own.
_MOVEMENT_TONE = {
    "opening_stock": "TEXT_TERTIARY",
    "purchase_receipt": "STATUS_HEALTHY",
    "return": "STATUS_HEALTHY",
    "sale": "TEXT_SECONDARY",
    "waste": "STATUS_CRITICAL",
    "adjustment": "STATUS_WARNING",
    "correction": "STATUS_WARNING",
    "transfer": "STATUS_INFO",
}

# Stock status -> translation key for the table's status chip.
_STATUS_LABELS = {
    "healthy": "status.in_stock",
    "low": "metric.low_stock",
    "out_of_stock": "status.out_of_stock",
    "near_expiry": "status.near_expiry",
    "expired": "status.expired",
    "at_risk": "status.at_risk",
}

# Alert severity -> translation key for the alert chip. The severity itself is a
# domain value ("critical"), so the chip must be translated rather than title-cased.
_SEVERITY_LABELS = {
    "critical": "severity.critical",
    "warning": "severity.warning",
    "info": "severity.info",
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
        t("nav.dashboard"),
        t("dashboard.subtitle"),
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
            ft.OutlinedButton(content=t("action.refresh"), icon=ft.Icons.REFRESH,
                              on_click=lambda e: navigate("/")),
        ],
    )

    out_of_stock = stats.out_of_stock_count
    kpis = kpi_strip([
        KpiMetric(t("metric.total_products"), str(stats.total_products), icon=ft.Icons.INVENTORY_2_OUTLINED,
                  accent=T.STATUS_INFO, caption=t("cap.in_catalogue"),
                  on_click=lambda e: navigate("/inventory")),
        KpiMetric(t("metric.total_stock_value"), format_money(stats.total_stock_value),
                  icon=ft.Icons.PAYMENTS_OUTLINED, accent=T.STATUS_HEALTHY, caption=t("cap.at_cost"),
                  on_click=lambda e: navigate("/inventory")),
        KpiMetric(t("metric.out_of_stock"), str(out_of_stock), icon=ft.Icons.REMOVE_SHOPPING_CART_OUTLINED,
                  accent=T.STATUS_CRITICAL,
                  caption=(f"{stats.low_stock_count} {t('metric.low_stock').lower()}"
                           if stats.low_stock_count else t("cap.requires_attention")),
                  delta_kind="down" if out_of_stock else "muted",
                  on_click=lambda e: navigate("/inventory")),
        KpiMetric(t("metric.expiry_risk"), str(stats.near_expiry_count),
                  icon=ft.Icons.EVENT_BUSY_OUTLINED, accent=T.STATUS_WARNING,
                  caption=t("cap.within_days", days=Config.NEAR_EXPIRY_WINDOW_DAYS),
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
    shown = list(alerts[:6])
    rows: list[ft.Control] = []
    for i, alert in enumerate(shown):
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
                trailing=status_chip(t(_SEVERITY_LABELS.get(alert.severity, "status.info")), status),
                on_click=lambda e, r=alert.route: navigate(r),
                divider=i < len(shown) - 1,
            )
        )

    content = (
        ft.Column(spacing=0, controls=rows)
        if rows
        else empty_state(t("empty.no_alerts"),
                         t("empty.no_alerts_body"),
                         icon=ft.Icons.CHECK_CIRCLE_OUTLINE)
    )
    return section(
        t("panel.recent_alerts"), content, subtitle=t("panel.alerts_subtitle"),
        actions=([ft.TextButton(content=t("action.view_all"), on_click=lambda e: navigate("/expiry"))] if rows else None),
    )


def _activity_panel(stats) -> ft.Control:
    shown = list(stats.recent_movements[:6])
    rows: list[ft.Control] = []
    for i, (product, movement) in enumerate(shown):
        delta = movement.quantity_delta
        positive = delta >= 0
        # ``movement_type`` is an enum in the domain but a plain str in some tests
        # and fixtures, so normalise rather than assume.
        kind = getattr(movement.movement_type, "value", movement.movement_type)
        tone = getattr(T, _MOVEMENT_TONE.get(kind, "TEXT_SECONDARY"))
        rows.append(
            list_row(
                leading=icon_tile(
                    ft.Icons.ARROW_UPWARD if positive else ft.Icons.ARROW_DOWNWARD,
                    color=tone,
                    size=30,
                ),
                title=product.name,
                subtitle=f"{t(_MOVEMENT_LABELS.get(kind, kind))}"
                         f" \u00b7 {movement.occurred_at}",
                trailing=ft.Text(f"{delta:+g}", size=T.FONT_BODY,
                                 color=tone, weight=ft.FontWeight.W_600),
                divider=i < len(shown) - 1,
            )
        )

    content = (
        ft.Column(spacing=0, controls=rows)
        if rows
        else empty_state(t("empty.no_movements"), t("empty.no_movements_body"),
                         icon=ft.Icons.SWAP_VERT)
    )
    return section(t("panel.recent_activity"), content, subtitle=t("panel.activity_subtitle"))


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
            t("panel.sales_vs_forecast"),
            empty_state(t("empty.no_forecasts"),
                        t("empty.no_forecasts_chart"),
                        icon=ft.Icons.INSIGHTS_OUTLINED),
            subtitle=t("panel.chart_units_subtitle"),
        )

    legend_items = [(t("chart.actual_sales"), T.PRIMARY), (t("chart.forecast"), T.ACCENT)]

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
        ft.Text(t("chart.band_note")
                if fc_upper else t("chart.band_hint"),
                size=T.FONT_TINY, color=T.TEXT_TERTIARY),
    ])
    return section(t("panel.sales_vs_forecast"), content, subtitle=t("panel.chart_units_subtitle"))


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
            ft.DataCell(status_chip(t(_STATUS_LABELS.get(status, status)), status)),
        ])
        for name, total, status in ranked[:6]
    ]
    content = styled_table([t("col.product"), t("col.forecast_7d"), t("col.stock_status")], rows,
                           empty_message=t("table.populate_forecasts"))
    return section(
        t("panel.top_demand"), content, subtitle=t("panel.top_products_sub"),
        actions=[ft.TextButton(content=t("action.view_all"), on_click=lambda e: navigate("/forecasting"))]
        if rows else None,
    )


def _quick_actions(navigate: Callable[[str], None]) -> ft.Control:
    def tile(icon: str, title: str, subtitle: str, route: str, accent: str) -> ft.Control:
        # No border and no fill: a quick action is a target, not a surface. The
        # ink ripple is the hover feedback, which is all it needs to read as
        # clickable.
        return ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(horizontal=10, vertical=10),
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
            tile(ft.Icons.ADD_CIRCLE_OUTLINE, t("quick.add_product"), t("quick.add_product_sub"),
                 "/inventory", T.STATUS_INFO),
            tile(ft.Icons.ADD_SHOPPING_CART_OUTLINED, t("quick.record_sale"), t("quick.record_sale_sub"),
                 "/sales", T.ACCENT),
        ]),
        ft.Row(spacing=T.GAP_SMALL, controls=[
            tile(ft.Icons.AUTO_GRAPH_OUTLINED, t("quick.generate_forecast"), t("quick.generate_forecast_sub"),
                 "/forecasting", T.STATUS_HEALTHY),
            tile(ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED, t("quick.reorder"),
                 t("quick.reorder_sub"), "/reorder", T.STATUS_WARNING),
        ]),
    ])
    return section(t("panel.quick_actions"), grid, subtitle=t("quick.jump"))


def _day_label(iso: str) -> str:
    return iso[8:10] if len(iso) >= 10 else iso
