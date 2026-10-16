"""StockWise — Sales view.

Records sales through a small cart. Sales and their stock movements are written
in one transaction by the service layer; overselling is blocked unless the user
explicitly opts into an audited override.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from domain.entities import Sale, SaleItem
from domain.exceptions import InsufficientStockError, StockWiseError
from domain.money import format_money, to_money
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import action_cell, styled_table, text_cell

_SOURCE_LABELS = {"manual": "Manual", "csv_import": "CSV import"}


def build_sales_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    products = list(app.product_service.list_products(active_only=True))
    usable = {p.id: app.inventory_service.usable_stock(p.id) for p in products}
    price_by_id = {str(p.id): p.selling_price for p in products}

    cart: list[dict] = []
    cart_holder = ft.Column(spacing=0)
    total_text = ft.Text(format_money(0), size=T.FONT_TITLE, weight=ft.FontWeight.BOLD, color=T.TEXT_PRIMARY)

    def render_cart(*, update: bool = True) -> None:
        rows = [
            ft.DataRow(cells=[
                text_cell(line["name"]),
                text_cell(f"{line['qty']:g}"),
                text_cell(format_money(line["price"]), color=T.TEXT_SECONDARY),
                text_cell(format_money(to_money(line["price"]) * Decimal(str(line["qty"])))),
                action_cell(lambda e, idx=idx: remove_line(idx), icon=ft.Icons.CLOSE, tooltip="Remove"),
            ])
            for idx, line in enumerate(cart)
        ]
        cart_holder.controls = [
            styled_table(["Product", "Qty", "Unit price", "Line total", ""], rows,
                         empty_message="Cart is empty \u2014 add a product to begin.")
        ]
        total = sum((to_money(l["price"]) * Decimal(str(l["qty"])) for l in cart), Decimal("0"))
        total_text.value = format_money(total)
        if update:
            cart_holder.update()

    def remove_line(idx: int) -> None:
        if 0 <= idx < len(cart):
            cart.pop(idx)
            render_cart()

    product_dd = dropdown_field(
        "Product",
        [(str(p.id), f"{p.name} \u00b7 {usable[p.id]:g} usable") for p in products]
        or [("__none__", "No products yet")],
        value=str(products[0].id) if products else "__none__", width=340,
        on_select=lambda e: _prefill_price(e, price_by_id, price_field),
    )
    price_field = text_field("Unit price (blank = product price)", width=200)
    qty_field = text_field("Quantity", value="1", width=140)
    date_field = text_field("Sale date/time (optional)", hint="YYYY-MM-DD HH:MM:SS", width=250)
    notes_field = text_field("Notes (optional)", width=250)
    override = ft.Checkbox(
        label="Allow overselling (audited override)",
        value=False,
        label_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
    )

    def add_to_cart(e) -> None:
        if not products or product_dd.value == "__none__":
            notify(page, "Add a product first", "warning")
            return
        product = next((p for p in products if str(p.id) == product_dd.value), None)
        if product is None:
            return
        try:
            qty = float((qty_field.value or "").strip())
            if qty <= 0:
                raise ValueError("Quantity must be greater than zero")
            price = (price_field.value or "").strip()
            unit_price = to_money(price) if price else product.selling_price
        except (ValueError, InvalidOperation):
            notify(page, "Enter a valid quantity", "error")
            return
        cart.append({"product_id": product.id, "name": product.name, "qty": qty, "price": unit_price})
        qty_field.value = "1"
        price_field.value = ""
        render_cart()

    def record(e) -> None:
        if not cart:
            notify(page, "Cart is empty", "warning")
            return
        sale = Sale(
            sold_at=(date_field.value or "").strip() or None,
            source="manual",
            notes=(notes_field.value or "").strip() or None,
            items=[SaleItem(product_id=l["product_id"], quantity=l["qty"], unit_price=l["price"]) for l in cart],
        )
        try:
            saved = app.sales_service.record_sale(sale, allow_override=bool(override.value))
            notify(page, f"Sale #{saved.id} recorded \u00b7 {format_money(saved.total_amount)}", "success")
            navigate("/sales")
        except InsufficientStockError as exc:
            notify(page, f"{exc}. Tick 'Allow overselling' to proceed.", "error")
        except StockWiseError as exc:
            notify_error(page, exc)

    render_cart(update=False)

    new_sale = section(
        "Record a sale",
        ft.Column(spacing=T.GAP, controls=[
            ft.Row(spacing=T.GAP_SMALL, wrap=True, controls=[product_dd, qty_field, price_field, ft.Button(content="Add to cart", icon=ft.Icons.ADD, on_click=add_to_cart)]),
            cart_holder,
            ft.Row(controls=[
                ft.Text("Total", size=T.FONT_SMALL, color=T.TEXT_SECONDARY),
                ft.Container(expand=True),
                total_text,
            ]),
            ft.Row(spacing=T.GAP_SMALL, wrap=True, controls=[date_field, notes_field]),
            override,
            ft.Row(spacing=T.GAP_SMALL, controls=[
                ft.Button(content="Record sale", icon=ft.Icons.CHECK, on_click=record),
                ft.OutlinedButton(content="Clear cart", on_click=lambda e: (cart.clear(), render_cart())),
            ]),
        ]),
    )

    recent = app.sales_service.list_recent(25)
    recent_rows = [
        ft.DataRow(cells=[
            text_cell(f"#{sale.id}"),
            text_cell((sale.sold_at or "")[:19], color=T.TEXT_SECONDARY),
            text_cell(_SOURCE_LABELS.get(sale.source, sale.source), color=T.TEXT_SECONDARY),
            text_cell(str(len(sale.items)), color=T.TEXT_SECONDARY),
            text_cell(format_money(sale.total_amount)),
            text_cell(sale.external_ref or "\u2014", color=T.TEXT_TERTIARY),
        ])
        for sale in recent
    ]
    recent_panel = section(
        "Recent sales",
        styled_table(["Sale", "When", "Source", "Items", "Total", "Reference"], recent_rows,
                     empty_message="No sales recorded yet."),
        subtitle=f"Latest {len(recent_rows)} sales",
    )

    return scroll_column([
        page_header("Sales", "Record counter sales and review recent transactions"),
        new_sale,
        recent_panel,
    ])


def _prefill_price(e, price_by_id: dict, price_field: ft.TextField) -> None:
    price = price_by_id.get(e.control.value)
    if price is not None:
        price_field.value = f"{price:.2f}"
        price_field.update()
