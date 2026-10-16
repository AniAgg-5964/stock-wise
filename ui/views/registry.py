"""StockWise — view registry.

Maps a route to its view builder. In Stage 1 every route resolves to a
placeholder; later stages replace entries with real views here (keeps
``main.py`` stable).
"""

from __future__ import annotations

from typing import Callable

import flet as ft

from ui.views.placeholder_views import build_placeholder_view

# route -> (title, description, icon)
VIEW_META: dict[str, tuple[str, str, str]] = {
    "/": ("Dashboard", "Daily overview of stock value, risks, demand and alerts.", ft.Icons.DASHBOARD_OUTLINED),
    "/inventory": ("Inventory", "Manage products, stock levels, batches and expiry.", ft.Icons.INVENTORY_2_OUTLINED),
    "/sales": ("Sales", "Record sales and import sales history.", ft.Icons.POINT_OF_SALE_OUTLINED),
    "/forecasting": ("Forecasting", "Generate and review demand forecasts.", ft.Icons.INSIGHTS_OUTLINED),
    "/reorder": ("Reorder Center", "Review replenishment recommendations.", ft.Icons.SHOPPING_CART_CHECKOUT_OUTLINED),
    "/expiry": ("Expiry Management", "Track batches by expiry and at-risk quantities.", ft.Icons.EVENT_BUSY_OUTLINED),
    "/suppliers": ("Supplier Research", "Research and verify supplier information.", ft.Icons.STOREFRONT_OUTLINED),
    "/reports": ("Reports", "Export sales, stock, forecast and purchasing reports.", ft.Icons.BAR_CHART_OUTLINED),
    "/settings": ("Settings", "Store, currency, alert policy, backup and diagnostics.", ft.Icons.SETTINGS_OUTLINED),
}


def build_view(route: str, page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    """Return the view control for a route."""
    title, description, icon = VIEW_META.get(route, VIEW_META["/"])
    return build_placeholder_view(page, navigate, title=title, description=description, icon=icon)
