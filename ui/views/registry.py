"""StockWise — view registry.

Maps a route to its view builder. Routes without a real view fall back to an
honest placeholder so navigation always works.
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ui.views.dashboard_view import build_dashboard_view
from ui.views.expiry_view import build_expiry_view
from ui.views.forecasting_view import build_forecasting_view
from ui.views.import_export_view import build_import_export_view
from ui.views.inventory_view import build_inventory_view
from ui.views.placeholder_views import build_placeholder_view
from ui.views.product_detail_view import build_product_detail_view
from ui.views.reorder_view import build_reorder_view
from ui.views.reports_view import build_reports_view
from ui.views.sales_view import build_sales_view
from ui.views.settings_view import build_settings_view
from ui.views.suppliers_view import build_suppliers_view

# route -> (title, description, icon)
VIEW_META: dict[str, tuple[str, str, str]] = {
    "/": ("Dashboard", "Daily overview of stock value, risks, demand and alerts.", ft.Icons.DASHBOARD_OUTLINED),
    "/inventory": ("Inventory", "Manage products, stock levels, batches and expiry.", ft.Icons.INVENTORY_2_OUTLINED),
    "/sales": ("Sales", "Record sales and import sales history.", ft.Icons.POINT_OF_SALE_OUTLINED),
    "/forecasting": ("Forecasting", "Generate and review demand forecasts.", ft.Icons.INSIGHTS_OUTLINED),
    "/reorder": ("Reorder Center", "Review replenishment recommendations.", ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED),
    "/expiry": ("Expiry Management", "Track batches by expiry and at-risk quantities.", ft.Icons.EVENT_BUSY_OUTLINED),
    "/suppliers": ("Supplier Research", "Research and verify supplier information.", ft.Icons.STOREFRONT_OUTLINED),
    "/reports": ("Reports", "Sales, stock, forecast and purchasing reports.", ft.Icons.BAR_CHART_OUTLINED),
    "/data": ("Data & Imports", "Import and export CSV data with validation.", ft.Icons.SWAP_VERT),
    "/settings": ("Settings", "Store, currency, alert policy, backup and diagnostics.", ft.Icons.SETTINGS_OUTLINED),
}

# Routes with a real view in this stage.
VIEW_BUILDERS: dict[str, Callable[[ft.Page, Callable[[str], None]], ft.Control]] = {
    "/": build_dashboard_view,
    "/inventory": build_inventory_view,
    "/sales": build_sales_view,
    "/forecasting": build_forecasting_view,
    "/reorder": build_reorder_view,
    "/expiry": build_expiry_view,
    "/suppliers": build_suppliers_view,
    "/reports": build_reports_view,
    "/data": build_import_export_view,
    "/settings": build_settings_view,
}


def build_view(route: str, page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    """Return the view control for a route."""
    if route.startswith("/product/"):
        try:
            product_id = int(route.rsplit("/", 1)[1])
        except ValueError:
            product_id = -1
        return build_product_detail_view(page, navigate, product_id)

    builder = VIEW_BUILDERS.get(route)
    if builder is not None:
        return builder(page, navigate)

    title, description, icon = VIEW_META.get(route, VIEW_META["/"])
    return build_placeholder_view(page, navigate, title=title, description=description, icon=icon)
