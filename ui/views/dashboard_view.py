"""StockWise — Dashboard view.

Every number on this screen is derived from real data. Panels that depend on
forecasting (which arrives in a later stage) show an honest "not available yet"
state instead of fabricated values.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from domain.money import format_money
from ui.components.empty_state import empty_state
from ui.components.kpi_card import kpi_card
from ui.components.layout import page_header, scroll_column, section
from ui.components.status_chip import status_chip

_MOVEMENT_LABELS = {
    "opening_stock": "Opening stock",
    "purchase_receipt": "Receipt",
    "sale": "Sale",
    "return": "Return",
    "waste": "Waste",
    "adjustment": "Adjustment",
    "correction": "Correction",
}


def build_dashboard_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    stats = app_context.dashboard_service.stats()

    header = page_header(
        "Dashboard",
        "Today's stock position across your store",
        actions=[
            ft.OutlinedButton(content="Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: navigate("/")),
        ],
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

    alerts = _alerts_panel(stats, navigate)
    activity = _activity_panel(stats)

    forecast_panel = section(
        "Sales vs Forecast",
        empty_state(
            "Forecasting arrives in the next stage",
            "Once forecasts are generated, predicted demand and stockout risk are charted here.",
            icon=ft.Icons.INSIGHTS_OUTLINED,
        ),
        subtitle="Uses the demand model \u2014 not yet enabled",
        expand=True,
    )
    top_products_panel = section(
        "Top Products by Predicted Demand",
        empty_state(
            "No forecasts yet",
            "This list fills in after the first forecast run.",
            icon=ft.Icons.LEADERBOARD_OUTLINED,
        ),
        expand=True,
    )

    quick_actions = section(
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

    return scroll_column([
        header,
        kpis,
        ft.Row(spacing=T.GAP, controls=[alerts, activity], vertical_alignment=ft.CrossAxisAlignment.START),
        ft.Row(spacing=T.GAP, controls=[forecast_panel, top_products_panel], vertical_alignment=ft.CrossAxisAlignment.START),
        quick_actions,
    ])


def _alerts_panel(stats, navigate: Callable[[str], None]) -> ft.Control:
    rows: list[ft.Control] = []

    for snap in stats.low_stock_items:
        label = "Out of stock" if snap.usable_stock <= 0 else "Low stock"
        rows.append(
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(spacing=1, expand=True, controls=[
                        ft.Text(snap.product.name, size=T.FONT_BODY, color=T.TEXT_PRIMARY),
                        ft.Text(
                            f"Usable {snap.usable_stock:g} \u00b7 reorder at {snap.product.reorder_point}",
                            size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                        ),
                    ]),
                    status_chip(label, snap.status),
                ],
            )
        )

    for product, batch in stats.expiring_batches:
        rows.append(
            ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(spacing=1, expand=True, controls=[
                        ft.Text(product.name, size=T.FONT_BODY, color=T.TEXT_PRIMARY),
                        ft.Text(
                            f"Batch {batch.batch_code or batch.id} \u00b7 expires {batch.expiry_date} "
                            f"\u00b7 {batch.quantity_remaining:g} units",
                            size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                        ),
                    ]),
                    status_chip("Near expiry", "near_expiry"),
                ],
            )
        )

    content = (
        ft.Column(spacing=T.GAP_SMALL, controls=rows)
        if rows
        else empty_state("Nothing needs attention", "No low-stock or expiring items right now.",
                         icon=ft.Icons.CHECK_CIRCLE_OUTLINE)
    )
    return section(
        "Alerts", content, subtitle="Low stock and expiry risks", expand=True,
        actions=[ft.TextButton(content="View all", on_click=lambda e: navigate("/expiry"))] if rows else None,
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
