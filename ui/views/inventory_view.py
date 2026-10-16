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
from domain.entities import Product
from domain.exceptions import StockWiseError
from domain.money import format_money
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import action_cell, chip_cell, styled_table, text_cell

_STATUS_FILTERS = [
    ("all", "All products"),
    ("low", "Low stock"),
    ("out_of_stock", "Out of stock"),
    ("near_expiry", "Near expiry"),
    ("expired", "Expired"),
]

_STATUS_LABELS = {
    "healthy": "Healthy",
    "low": "Low",
    "out_of_stock": "Out of stock",
    "near_expiry": "Near expiry",
    "expired": "Expired",
    "at_risk": "At risk",
}


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
            rows.append(
                ft.DataRow(cells=[
                    ft.DataCell(ft.Column(spacing=1, tight=True, controls=[
                        ft.Text(product.name, size=T.FONT_BODY, color=T.TEXT_PRIMARY,
                                weight=ft.FontWeight.W_500),
                        ft.Text(product.sku + ("" if product.active else " \u00b7 archived"),
                                size=T.FONT_TINY, color=T.TEXT_TERTIARY),
                    ])),
                    text_cell(product.category, color=T.TEXT_SECONDARY),
                    text_cell(f"{snap.usable_stock:g} {product.unit}"),
                    chip_cell(_STATUS_LABELS.get(snap.status, snap.status), snap.status),
                    text_cell(str(product.reorder_point), color=T.TEXT_SECONDARY),
                    text_cell(format_money(product.selling_price), color=T.TEXT_SECONDARY),
                    action_cell(lambda e, pid=product.id: navigate(f"/product/{pid}"), tooltip="Open product"),
                ])
            )

        table_holder.controls = [
            styled_table(
                ["Product", "Category", "Usable", "Status", "Reorder", "Price", ""],
                rows, empty_message="No products match these filters.",
            )
        ]
        count_text.value = f"{len(rows)} of {len(products)} products"
        if update:
            table_holder.update()

    categories = app.product_service.list_categories()
    category_options = [("__all__", "All categories")] + [(c, c) for c in categories]

    search = text_field("Search products", hint="Name, SKU or brand\u2026", width=300,
                        on_change=lambda e: (state.update(search=e.control.value), render_table()))
    category = dropdown_field("Category", category_options, value="__all__", width=220,
                              on_select=lambda e: (
                                  state.update(category=None if e.control.value == "__all__" else e.control.value),
                                  render_table(),
                              ))
    status = dropdown_field("Status", _STATUS_FILTERS, value="all", width=200,
                            on_select=lambda e: (state.update(status=e.control.value or "all"), render_table()))

    render_table(update=False)

    header = page_header(
        "Inventory",
        "Products, stock levels and expiry status",
        actions=[
            ft.OutlinedButton(content="Import / Export", icon=ft.Icons.SWAP_VERT,
                              on_click=lambda e: navigate("/reports")),
            ft.Button(content="Add product", icon=ft.Icons.ADD, on_click=lambda e: _open_add_product(page, navigate)),
        ],
    )

    toolbar = ft.Row(spacing=T.GAP, controls=[search, category, status, ft.Container(expand=True), count_text])

    return scroll_column([
        header,
        toolbar,
        section("Product catalogue", table_holder),
    ])


def _open_add_product(page: ft.Page, navigate: Callable[[str], None]) -> None:
    app = app_context
    fields = {
        "sku": text_field("SKU *", width=250, autofocus=True),
        "name": text_field("Product name *", width=250),
        "category": text_field("Category", value="General", width=250),
        "unit": text_field("Unit", value="pcs", width=250),
        "brand": text_field("Brand", width=250),
        "cost": text_field("Cost price", value="0", width=250),
        "price": text_field("Selling price", value="0", width=250),
        "reorder": text_field("Reorder point", value="10", width=250),
        "safety": text_field("Safety stock", value="5", width=250),
        "opening": text_field("Opening stock", value="0", width=250),
        "expiry": text_field("Expiry date (YYYY-MM-DD, optional)", width=250),
    }
    expiry_switch = ft.Switch(label="Track expiry for this product", value=False,
                              label_text_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL))
    suppliers = app.supplier_service.list_suppliers()
    supplier_dd = dropdown_field("Preferred supplier (optional)",
                                 [("__none__", "None")] + [(str(s.id), s.name) for s in suppliers], value="__none__")

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
        title=ft.Text("Add product"),
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
            ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
            ft.Button(content="Save product", on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
