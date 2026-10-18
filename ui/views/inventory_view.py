"""StockWise — Inventory view.

Lists products with live stock and status, supports search/filter, and adds new
products. Row actions open the product detail screen. No SQL or ML here.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from app.i18n import t
from domain.entities import Product
from domain.exceptions import StockWiseError
from domain.money import format_money
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, search_field, text_field
from ui.components.kpi_card import KpiMetric, kpi_strip
from ui.components.layout import flow_row, page_header, scroll_column, section
from ui.components.table import action_cell, chip_cell, entity_cell, styled_table, text_cell

_STATUS_FILTERS = [
    ("all", "All products"),
    ("low", "Low stock"),
    ("out_of_stock", "Out of stock"),
    ("near_expiry", "Near expiry"),
    ("expired", "Expired"),
]

_STATUS_LABELS = {
    "healthy": "In stock",
    "low": "Low stock",
    "out_of_stock": "Out of stock",
    "near_expiry": "Near expiry",
    "expired": "Expired",
    "at_risk": "At risk",
}

_CATEGORY_EMOJI = {
    "dairy": "\U0001F95B",
    "bakery": "\U0001F35E",
    "beverages": "\U0001F964",
    "snacks": "\U0001F36A",
    "staples": "\U0001F35A",
    "personal care": "\U0001F9F4",
    "household": "\U0001F9F9",
    "sweets": "\U0001F36C",
    "frozen": "\U0001F9CA",
}


def _category_emoji(category: str) -> str:
    return _CATEGORY_EMOJI.get((category or "").strip().lower(), "\U0001F4E6")


def _dec(value: str, default: str = "0") -> Decimal:
    text = (value or "").strip()
    if not text:
        return Decimal(default)
    return Decimal(text)


def _int(value: str, default: int = 0) -> int:
    try:
        return int(float((value or "").strip() or default))
    except (TypeError, ValueError):
        return default


def _float(value: str, default: float = 0.0) -> float:
    try:
        return float((value or "").strip() or default)
    except (TypeError, ValueError):
        return default


def _stock_color(status: str) -> str:
    return {
        "out_of_stock": T.STATUS_CRITICAL,
        "expired": T.STATUS_CRITICAL,
        "low": T.STATUS_WARNING,
        "near_expiry": T.STATUS_WARNING,
    }.get(status, T.TEXT_PRIMARY)


def build_inventory_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    state = {"search": "", "category": None, "status": "all"}

    table_holder = ft.Column(spacing=0)
    count_text = ft.Text("", size=T.FONT_TINY, color=T.TEXT_TERTIARY)

    def render_table(*, update: bool = True) -> None:
        products = list(app.product_service.list_products(
            active_only=False,
            category=state["category"],
            search_query=state["search"] or None,
        ))
        snapshots = app.inventory_service.snapshots_for_products(products)
        if state["status"] != "all":
            snapshots = [s for s in snapshots if s.status == state["status"]]

        rows: list[ft.DataRow] = []
        for snap in snapshots:
            product = snap.product
            stock_color = _stock_color(snap.status)
            rows.append(
                ft.DataRow(cells=[
                    entity_cell(
                        product.name,
                        None if product.active else "archived",
                        leading=ft.Container(
                            width=32, height=32,
                            border_radius=T.RADIUS_SMALL,
                            bgcolor=T.BG_INPUT,
                            alignment=ft.Alignment.CENTER,
                            content=ft.Text(_category_emoji(product.category), size=16),
                        ),
                    ),
                    text_cell(product.sku, color=T.TEXT_SECONDARY),
                    text_cell(product.category, color=T.TEXT_SECONDARY),
                    text_cell(f"{snap.usable_stock:g} {product.unit}", color=stock_color,
                              weight=ft.FontWeight.W_600),
                    text_cell(format_money(product.selling_price), color=T.TEXT_SECONDARY),
                    chip_cell(_STATUS_LABELS.get(snap.status, snap.status), snap.status),
                    action_cell(lambda e, pid=product.id: navigate(f"/product/{pid}"),
                                tooltip=t("action.view_all")),
                ])
            )

        table_holder.controls = [
            styled_table(
                ["Product", "SKU", t("field.category"), "Stock", "Price", t("field.status"), ""],
                rows, empty_message=t("empty.no_filters"),
            )
        ]
        count_text.value = f"{len(rows)} of {len(products)} products"
        if update:
            table_holder.update()

    categories = app.product_service.list_categories()
    category_options = [("__all__", "All categories")] + [(c, c) for c in categories]

    search = search_field(t("field.search_products"), width=280,
                          on_change=lambda e: (state.update(search=e.control.value), render_table()))
    category = dropdown_field(t("field.category"), category_options, value="__all__", width=210,
                              dense=True,
                              on_select=lambda e: (
                                  state.update(category=None if e.control.value == "__all__" else e.control.value),
                                  render_table(),
                              ))
    status = dropdown_field(t("field.status"), _STATUS_FILTERS, value="all", width=190, dense=True,
                            on_select=lambda e: (state.update(status=e.control.value or "all"), render_table()))

    render_table(update=False)

    # --- KPI counts (always global, regardless of the active filters) ---
    all_snapshots = app.inventory_service.snapshots_for_products(
        app.product_service.list_products(active_only=False)
    )
    low = sum(1 for s in all_snapshots if s.status == "low")
    out = sum(1 for s in all_snapshots if s.status == "out_of_stock")

    kpis = kpi_strip([
        KpiMetric("Total Products", str(len(all_snapshots)), icon=ft.Icons.INVENTORY_2_OUTLINED,
                  accent=T.STATUS_INFO, caption="In the catalogue"),
        KpiMetric("Low Stock", str(low), icon=ft.Icons.WARNING_AMBER_OUTLINED,
                  accent=T.STATUS_WARNING, caption="At or below reorder point",
                  delta_kind="warn" if low else "muted",
                  on_click=lambda e: _set_filter(status, state, render_table, "low")),
        KpiMetric("Out of Stock", str(out), icon=ft.Icons.REMOVE_SHOPPING_CART_OUTLINED,
                  accent=T.STATUS_CRITICAL, caption="Needs restocking",
                  delta_kind="down" if out else "muted",
                  on_click=lambda e: _set_filter(status, state, render_table, "out_of_stock")),
        KpiMetric("Categories", str(len(categories)), icon=ft.Icons.CATEGORY_OUTLINED,
                  accent=T.ACCENT, caption="Product groups"),
    ])

    header = page_header(
        t("nav.inventory"),
        "Manage your products and stock levels \u2014 add, edit or remove products and track expiry.",
        actions=[
            ft.OutlinedButton(content=t("panel.import_export"), icon=ft.Icons.SWAP_VERT,
                              on_click=lambda e: navigate("/data")),
            ft.Button(content=t("action.add_product_title"), icon=ft.Icons.ADD,
                      on_click=lambda e: _open_add_product(page, navigate)),
        ],
    )

    toolbar = flow_row([
        (search, {"xs": 12, "sm": 12, "lg": 6}),
        (category, {"xs": 12, "sm": 6, "lg": 3}),
        (status, {"xs": 12, "sm": 6, "lg": 3}),
    ])

    return scroll_column([
        header,
        kpis,
        section(
            t("panel.product_catalogue"),
            ft.Column(spacing=T.GAP_SMALL, controls=[toolbar, table_holder]),
            subtitle=count_text,
        ),
    ])


def _set_filter(status_control, state: dict, render_table, value: str) -> None:
    state["status"] = value
    status_control.value = value
    try:
        status_control.update()
    except Exception:  # pragma: no cover - defensive
        pass
    render_table()


def _open_add_product(page: ft.Page, navigate: Callable[[str], None]) -> None:
    app = app_context
    fields = {
        "sku": text_field(t("field.sku"), width=250, autofocus=True),
        "name": text_field(t("field.product_name"), width=250),
        "category": text_field(t("field.category"), value="General", width=250),
        "unit": text_field(t("field.unit"), value="pcs", width=250),
        "brand": text_field(t("field.brand"), width=250),
        "cost": text_field(t("field.cost_price"), value="0", width=250),
        "price": text_field(t("field.selling_price"), value="0", width=250),
        "reorder": text_field(t("field.reorder_point"), value="10", width=250),
        "safety": text_field(t("field.safety_stock"), value="5", width=250),
        "opening": text_field(t("field.opening_stock"), value="0", width=250),
        "expiry": text_field(t("field.expiry_date"), width=250),
    }
    expiry_switch = ft.Switch(label=t("field.track_expiry"), value=False,
                              label_text_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL))
    suppliers = app.supplier_service.list_suppliers()
    supplier_dd = dropdown_field(t("field.preferred_supplier"),
                                 [("__none__", "None")] + [(str(s.id), s.name) for s in suppliers],
                                 value="__none__")

    def save(e) -> None:
        try:
            product = app.product_service.create_product(Product(
                sku=fields["sku"].value, name=fields["name"].value,
                category=(fields["category"].value or "General").strip(),
                unit=(fields["unit"].value or "pcs").strip(),
                brand=(fields["brand"].value or "").strip() or None,
                cost_price=_dec(fields["cost"].value), selling_price=_dec(fields["price"].value),
                reorder_point=_int(fields["reorder"].value, 10), safety_stock=_int(fields["safety"].value, 5),
                expiry_tracking=bool(expiry_switch.value),
            ))
            opening = _float(fields["opening"].value)
            if opening > 0:
                app.inventory_service.receive_stock(
                    product.id, opening,
                    unit_cost=_dec(fields["cost"].value),
                    expiry_date=(fields["expiry"].value or "").strip() or None,
                    reason="Opening stock (added with product)",
                    source_type="product_create", source_id=f"opening-{product.id}",
                )
            if supplier_dd.value and supplier_dd.value != "__none__":
                from domain.entities import ProductSupplier

                app.supplier_service.link_product_supplier(
                    ProductSupplier(product_id=product.id, supplier_id=int(supplier_dd.value), is_preferred=True)
                )
            page.pop_dialog()
            notify(page, f"Added '{product.name}'", "success")
            navigate("/inventory")
        except (StockWiseError, InvalidOperation, ValueError) as exc:
            notify_error(page, exc)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(t("action.add_product")),
        content=ft.Container(
            width=560,
            content=ft.Column(
                scroll=ft.ScrollMode.AUTO,
                tight=True,
                spacing=T.GAP_SMALL,
                controls=[
                    ft.Row(spacing=T.GAP_SMALL, controls=[fields["sku"], fields["name"]]),
                    ft.Row(spacing=T.GAP_SMALL, controls=[fields["category"], fields["unit"]]),
                    ft.Row(spacing=T.GAP_SMALL, controls=[fields["brand"], fields["reorder"]]),
                    ft.Row(spacing=T.GAP_SMALL, controls=[fields["cost"], fields["price"]]),
                    ft.Row(spacing=T.GAP_SMALL, controls=[fields["safety"], fields["opening"]]),
                    expiry_switch,
                    fields["expiry"],
                    supplier_dd,
                ],
            ),
        ),
        actions=[
            ft.TextButton(content=t("action.cancel"), on_click=lambda e: page.pop_dialog()),
            ft.Button(content=t("action.save_product"), on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
