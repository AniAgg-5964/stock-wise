"""StockWise — Product detail view.

Shows one product's metadata, live stock, batches and immutable movement ledger,
and hosts the stock actions (adjust / waste / edit).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from domain.entities import Product
from domain.exceptions import StockWiseError
from domain.money import format_money
from ui.components.empty_state import empty_state
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.kpi_card import kpi_card
from ui.components.layout import page_header, scroll_column, section
from ui.components.status_chip import status_chip
from ui.components.table import chip_cell, styled_table, text_cell

_MOVEMENT_LABELS = {
    "opening_stock": "Opening stock",
    "purchase_receipt": "Receipt",
    "sale": "Sale",
    "return": "Return",
    "waste": "Waste",
    "adjustment": "Adjustment",
    "correction": "Correction",
}


def _dec(value: str, default: str = "0") -> Decimal:
    text = (value or "").strip()
    return Decimal(text) if text else Decimal(default)


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


def build_product_detail_view(page: ft.Page, navigate: Callable[[str], None], product_id: int) -> ft.Control:
    app = app_context
    product = app.product_service.get_product(product_id)
    if product is None:
        return ft.Column(controls=[
            page_header("Product not found", "It may have been removed"),
            empty_state("Product not found", "Return to the inventory list and pick another product.",
                        action=ft.Button(content="Back to inventory", on_click=lambda e: navigate("/inventory"))),
        ], expand=True)

    snapshot = app.inventory_service.stock_snapshot(product)
    batches = list(app.inventory_service.get_batches(product.id, include_depleted=True))
    movements = list(app.inventory_service.get_movements(product.id, limit=50))
    links = list(app.supplier_service.get_product_suppliers(product.id))

    header = page_header(
        product.name,
        f"{product.sku} \u00b7 {product.category}",
        actions=[
            ft.TextButton(content="Back", icon=ft.Icons.ARROW_BACK, on_click=lambda e: navigate("/inventory")),
            ft.OutlinedButton(content="Edit", icon=ft.Icons.EDIT_OUTLINED,
                              on_click=lambda e: _open_edit(page, product, navigate)),
            ft.OutlinedButton(content="Adjust stock", icon=ft.Icons.TUNE,
                              on_click=lambda e: _open_adjust(page, product, navigate)),
            ft.Button(content="Record waste", icon=ft.Icons.DELETE_OUTLINE,
                      on_click=lambda e: _open_waste(page, product, navigate)),
        ],
    )

    stock_value = sum(
        (Decimal(str(b.quantity_remaining)) * (b.unit_cost or Decimal("0")))
        for b in batches if b.quantity_remaining > 0
    )
    kpis = ft.Row(spacing=T.GAP, controls=[
        kpi_card("Usable stock", f"{snapshot.usable_stock:g}", subtitle=f"in {product.unit}",
                 accent=T.STATUS_HEALTHY),
        kpi_card("On hand (ledger)", f"{snapshot.stock_level:g}", subtitle="physical units",
                 accent=T.STATUS_INFO),
        kpi_card("Batches", str(snapshot.batch_count), subtitle="active batches", accent=T.PRIMARY),
        kpi_card("Stock value", format_money(stock_value), subtitle="at batch cost",
                 accent=T.STATUS_WARNING),
    ])

    details = section(
        "Product details",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            _detail_row("Status", status_chip(_status_label(snapshot.status), snapshot.status)),
            _detail_row("Brand", ft.Text(product.brand or "\u2014", color=T.TEXT_PRIMARY)),
            _detail_row("Unit", ft.Text(product.unit, color=T.TEXT_PRIMARY)),
            _detail_row("Cost price", ft.Text(format_money(product.cost_price), color=T.TEXT_PRIMARY)),
            _detail_row("Selling price", ft.Text(format_money(product.selling_price), color=T.TEXT_PRIMARY)),
            _detail_row("Reorder point", ft.Text(str(product.reorder_point), color=T.TEXT_PRIMARY)),
            _detail_row("Safety stock", ft.Text(str(product.safety_stock), color=T.TEXT_PRIMARY)),
            _detail_row("Expiry tracking", ft.Text("On" if product.expiry_tracking else "Off", color=T.TEXT_PRIMARY)),
            _detail_row("Nearest expiry", ft.Text(snapshot.nearest_expiry or "\u2014", color=T.TEXT_PRIMARY)),
        ]),
        expand=True,
    )

    supplier_rows = ft.Column(spacing=T.GAP_SMALL, controls=[
        ft.Row(controls=[
            ft.Column(spacing=1, expand=True, controls=[
                ft.Text(supplier.name, size=T.FONT_BODY, color=T.TEXT_PRIMARY,
                        weight=ft.FontWeight.W_500),
                ft.Text(
                    f"Lead {link.lead_time_days}d \u00b7 MOQ {link.minimum_order_qty} \u00b7 pack {link.pack_size}",
                    size=T.FONT_TINY, color=T.TEXT_TERTIARY,
                ),
            ]),
            status_chip("Preferred", "healthy") if link.is_preferred else status_chip("Backup", "neutral"),
        ])
        for link, supplier in links
    ]) if links else empty_state("No suppliers linked", "Link a supplier from the Supplier Research screen.",
                                 icon=ft.Icons.STOREFRONT_OUTLINED)
    suppliers_panel = section("Suppliers", supplier_rows, expand=True)

    batch_rows = [
        ft.DataRow(cells=[
            text_cell(b.batch_code or f"#{b.id}"),
            text_cell((b.received_at or "")[:10], color=T.TEXT_SECONDARY),
            text_cell(b.expiry_date or "\u2014", color=T.TEXT_SECONDARY),
            text_cell(f"{b.quantity_received:g}", color=T.TEXT_SECONDARY),
            text_cell(f"{b.quantity_remaining:g}"),
            text_cell(format_money(b.unit_cost or 0), color=T.TEXT_SECONDARY),
            chip_cell(*_batch_status(b.expiry_date)),
        ])
        for b in batches
    ]
    batches_panel = section(
        "Batches (FEFO order)",
        styled_table(["Batch", "Received", "Expiry", "Received qty", "Remaining", "Unit cost", "Status"],
                     batch_rows, empty_message="No batches received yet."),
    )

    movement_rows = [
        ft.DataRow(cells=[
            text_cell((m.occurred_at or "")[:19], color=T.TEXT_SECONDARY),
            text_cell(_MOVEMENT_LABELS.get(m.movement_type, m.movement_type)),
            text_cell(f"{m.quantity_delta:+g}",
                      color=T.STATUS_HEALTHY if m.quantity_delta >= 0 else T.STATUS_CRITICAL),
            text_cell(f"{m.balance_after:g}"),
            text_cell(m.reason or "\u2014", color=T.TEXT_TERTIARY),
        ])
        for m in movements
    ]
    movements_panel = section(
        "Stock movement ledger",
        styled_table(["When", "Type", "Change", "Balance", "Reason"], movement_rows,
                     empty_message="No movements recorded."),
        subtitle="Append-only \u2014 corrections are new records, never rewrites",
    )

    return scroll_column([
        header,
        kpis,
        ft.Row(spacing=T.GAP, controls=[details, suppliers_panel], vertical_alignment=ft.CrossAxisAlignment.START),
        batches_panel,
        movements_panel,
    ])


def _detail_row(label: str, control: ft.Control) -> ft.Control:
    return ft.Row(controls=[
        ft.Text(label, size=T.FONT_SMALL, color=T.TEXT_SECONDARY, width=140),
        ft.Container(content=control, expand=True),
    ])


def _status_label(status: str) -> str:
    return {
        "healthy": "Healthy", "low": "Low", "out_of_stock": "Out of stock",
        "near_expiry": "Near expiry", "expired": "Expired", "at_risk": "At risk",
    }.get(status, status)


def _batch_status(expiry: str | None) -> tuple[str, str]:
    if not expiry:
        return "No expiry", "neutral"
    today = date.today()
    if expiry < today.isoformat():
        return "Expired", "expired"
    if expiry <= (today + timedelta(days=7)).isoformat():
        return "Near expiry", "near_expiry"
    return "OK", "healthy"


# --------------------------------------------------------------------------- dialogs
def _open_edit(page: ft.Page, product: Product, navigate: Callable[[str], None]) -> None:
    app = app_context
    fields = {
        "sku": text_field("SKU *", value=product.sku, width=250),
        "name": text_field("Product name *", value=product.name, width=250),
        "category": text_field("Category", value=product.category, width=250),
        "unit": text_field("Unit", value=product.unit, width=250),
        "brand": text_field("Brand", value=product.brand or "", width=250),
        "cost": text_field("Cost price", value=str(product.cost_price), width=250),
        "price": text_field("Selling price", value=str(product.selling_price), width=250),
        "reorder": text_field("Reorder point", value=str(product.reorder_point), width=250),
        "safety": text_field("Safety stock", value=str(product.safety_stock), width=250),
    }
    expiry_switch = ft.Switch(label="Track expiry", value=product.expiry_tracking,
                              label_text_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL))

    def save(e) -> None:
        try:
            app.product_service.update_product(Product(
                id=product.id, sku=fields["sku"].value, name=fields["name"].value,
                category=(fields["category"].value or "General").strip(),
                unit=(fields["unit"].value or "pcs").strip(),
                brand=(fields["brand"].value or "").strip() or None,
                cost_price=_dec(fields["cost"].value), selling_price=_dec(fields["price"].value),
                reorder_point=_int(fields["reorder"].value, 10), safety_stock=_int(fields["safety"].value, 5),
                expiry_tracking=bool(expiry_switch.value), active=product.active,
            ))
            page.pop_dialog()
            notify(page, "Product updated", "success")
            navigate(f"/product/{product.id}")
        except (StockWiseError, InvalidOperation, ValueError) as exc:
            notify_error(page, exc)

    _show_form(page, "Edit product", [
        ft.Row(spacing=T.GAP_SMALL, controls=[fields["sku"], fields["name"]]),
        ft.Row(spacing=T.GAP_SMALL, controls=[fields["category"], fields["unit"]]),
        ft.Row(spacing=T.GAP_SMALL, controls=[fields["brand"], fields["reorder"]]),
        ft.Row(spacing=T.GAP_SMALL, controls=[fields["cost"], fields["price"]]),
        ft.Row(spacing=T.GAP_SMALL, controls=[fields["safety"]]),
        expiry_switch,
    ], save)


def _open_adjust(page: ft.Page, product: Product, navigate: Callable[[str], None]) -> None:
    app = app_context
    delta = text_field("Quantity change (use negative to reduce) *", value="0", width=340)
    reason = text_field("Reason *", width=340)

    def save(e) -> None:
        try:
            app.inventory_service.adjust_stock(
                product.id, _float(delta.value), reason=(reason.value or "").strip()
            )
            page.pop_dialog()
            notify(page, "Stock adjusted", "success")
            navigate(f"/product/{product.id}")
        except (StockWiseError, ValueError) as exc:
            notify_error(page, exc)

    _show_form(page, f"Adjust stock \u2014 {product.name}", [delta, reason], save)


def _open_waste(page: ft.Page, product: Product, navigate: Callable[[str], None]) -> None:
    app = app_context
    batches = app.inventory_service.get_batches(product.id, include_depleted=False)
    batch_dd = dropdown_field(
        "Batch",
        [(str(b.id), f"{b.batch_code or '#' + str(b.id)} \u00b7 exp {b.expiry_date or '\u2014'} \u00b7 {b.quantity_remaining:g}")
         for b in batches] or [("__none__", "No batches available")],
        value=str(batches[0].id) if batches else "__none__", width=380,
    )
    quantity = text_field("Quantity *", width=380)
    reason = text_field("Reason * (e.g. spoilage, expired)", width=380)

    def save(e) -> None:
        try:
            batch_id = None if batch_dd.value == "__none__" else int(batch_dd.value)
            app.inventory_service.record_waste(
                product.id, _float(quantity.value), reason=(reason.value or "").strip(), batch_id=batch_id
            )
            page.pop_dialog()
            notify(page, "Waste recorded", "success")
            navigate(f"/product/{product.id}")
        except (StockWiseError, ValueError) as exc:
            notify_error(page, exc)

    _show_form(page, f"Record waste \u2014 {product.name}", [batch_dd, quantity, reason], save)


def _show_form(page: ft.Page, title: str, controls: list[ft.Control], on_save: Callable) -> None:
    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Container(width=420, content=ft.Column(tight=True, spacing=T.GAP_SMALL, controls=controls)),
        actions=[
            ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
            ft.Button(content="Save", on_click=on_save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
