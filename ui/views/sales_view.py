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
from app.i18n import t
from domain.entities import Sale, SaleItem
from domain.exceptions import InsufficientStockError, StockWiseError
from domain.money import format_money, to_money
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.layout import flow_row, page_header, scroll_column, section
from ui.components.table import action_cell, styled_table, text_cell

def _source_labels() -> dict[str, str]:
    """Per call so a language switch reaches the ledger."""
    return {"manual": t("sale.source_manual"), "csv_import": t("sale.source_csv")}


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
                action_cell(lambda e, idx=idx: remove_line(idx), icon=ft.Icons.CLOSE, tooltip=t("action.remove")),
            ])
            for idx, line in enumerate(cart)
        ]
        cart_holder.controls = [
            styled_table([t("col.product"), t("col.qty"), t("col.unit_price"), t("col.line_total"), ""], rows,
                         empty_message=t("empty.cart"))
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
        t("col.product"),
        [(str(p.id), f"{p.name} " + t("sale.usable_suffix", qty=f"{usable[p.id]:g}"))
         for p in products]
        or [("__none__", "No products yet")],
        value=str(products[0].id) if products else "__none__", width=340,
        on_select=lambda e: _prefill_price(e, price_by_id, price_field),
    )
    price_field = text_field(t("field.unit_price"), width=200)
    qty_field = text_field(t("field.quantity"), value="1", width=140)
    date_field = text_field(t("field.sale_datetime"), hint=t("hint.datetime"), width=250)
    notes_field = text_field(t("field.notes_optional"), width=250)
    override = ft.Checkbox(
        label=t("field.oversell"),
        value=False,
        label_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL),
    )

    def add_to_cart(e) -> None:
        if not products or product_dd.value == "__none__":
            notify(page, t("empty.add_product_first"), "warning")
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
            notify(page, t("empty.invalid_qty"), "error")
            return
        cart.append({"product_id": product.id, "name": product.name, "qty": qty, "price": unit_price})
        qty_field.value = "1"
        price_field.value = ""
        render_cart()

    def record(e) -> None:
        if not cart:
            notify(page, t("empty.cart_short"), "warning")
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
        t("panel.record_sale"),
        ft.Column(spacing=T.GAP, controls=[
            flow_row([product_dd, qty_field, price_field, ft.Button(content=t("action.add_to_cart"), icon=ft.Icons.ADD, on_click=add_to_cart)]),
            cart_holder,
            ft.Row(controls=[
                ft.Text(t("label.total"), size=T.FONT_SMALL, color=T.TEXT_SECONDARY),
                ft.Container(expand=True),
                total_text,
            ]),
            flow_row([date_field, notes_field], col={"xs": 12, "sm": 6, "lg": 6}),
            override,
            ft.Row(spacing=T.GAP_SMALL, controls=[
                ft.Button(content=t("action.record_sale"), icon=ft.Icons.CHECK, on_click=record),
                ft.OutlinedButton(content=t("action.clear_cart"), on_click=lambda e: (cart.clear(), render_cart())),
            ]),
        ]),
    )

    recent = app.sales_service.list_recent(25)
    recent_rows = [
        ft.DataRow(cells=[
            text_cell(f"#{sale.id}"),
            text_cell((sale.sold_at or "")[:19], color=T.TEXT_SECONDARY),
            text_cell(_source_labels().get(sale.source, sale.source), color=T.TEXT_SECONDARY),
            text_cell(str(len(sale.items)), color=T.TEXT_SECONDARY),
            text_cell(format_money(sale.total_amount)),
            text_cell(sale.external_ref or "\u2014", color=T.TEXT_TERTIARY),
        ])
        for sale in recent
    ]
    recent_panel = section(
        t("panel.recent_sales"),
        styled_table([t("col.sale"), t("col.when"), t("col.source"), t("col.items"), t("label.total"),
         t("col.reference")], recent_rows,
                     empty_message=t("empty.no_sales")),
        subtitle=t("panel.latest_sales", count=len(recent_rows)),
    )

    return scroll_column([
        page_header(t("nav.sales"), t("dashboard.sales_subtitle")),
        new_sale,
        recent_panel,
    ])


def _prefill_price(e, price_by_id: dict, price_field: ft.TextField) -> None:
    price = price_by_id.get(e.control.value)
    if price is not None:
        price_field.value = f"{price:.2f}"
        price_field.update()
