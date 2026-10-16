"""StockWise — Expiry management view.

Lists batches by expiry (soonest first), separates already-expired stock, and
lets the user write off a batch as waste. Expired stock is never sellable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.theme import StockWiseTheme as T
from domain.exceptions import StockWiseError
from domain.money import format_money
from ui.components.empty_state import empty_state
from ui.components.feedback import notify, notify_error
from ui.components.forms import text_field
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import action_cell, chip_cell, styled_table, text_cell


def _days_left(expiry: str | None) -> int | None:
    if not expiry:
        return None
    try:
        target = date.fromisoformat(expiry)
    except ValueError:
        return None
    return (target - date.today()).days


def build_expiry_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    window = int(float(app.settings.get("near_expiry_window_days", str(Config.NEAR_EXPIRY_WINDOW_DAYS)) or 7))

    expiring = list(app.inventory_service.expiring_batches(window))
    expired = list(app.inventory_service.expired_batches())

    def build_rows(batches, *, expired_rows: bool):
        rows = []
        for batch in batches:
            product = app.product_service.get_product(batch.product_id)
            name = product.name if product else f"Product {batch.product_id}"
            left = _days_left(batch.expiry_date)
            if expired_rows:
                label, status = "Expired", "expired"
                left_text = f"{abs(left)}d ago" if left is not None else "\u2014"
            else:
                label, status = "Near expiry", "near_expiry"
                left_text = f"{left}d" if left is not None else "\u2014"
            rows.append(ft.DataRow(cells=[
                text_cell(name),
                text_cell(batch.batch_code or f"#{batch.id}", color=T.TEXT_SECONDARY),
                text_cell(batch.expiry_date or "\u2014", color=T.TEXT_SECONDARY),
                text_cell(left_text, color=T.TEXT_SECONDARY),
                text_cell(f"{batch.quantity_remaining:g}"),
                text_cell(format_money((batch.unit_cost or Decimal("0")) * Decimal(str(batch.quantity_remaining))), color=T.TEXT_SECONDARY),
                chip_cell(label, status),
                action_cell(lambda e, b=batch, p=product: _open_waste(page, navigate, b, p),
                            icon=ft.Icons.DELETE_OUTLINE, tooltip="Record waste"),
            ]))
        return rows

    expiring_panel = section(
        f"Expiring within {window} days",
        styled_table(["Product", "Batch", "Expiry", "Days left", "Remaining", "Value", "Status", ""],
                     build_rows(expiring, expired_rows=False),
                     empty_message="Nothing expiring in this window."),
    )
    expired_panel = section(
        "Already expired",
        styled_table(["Product", "Batch", "Expiry", "Days over", "Remaining", "Value", "Status", ""],
                     build_rows(expired, expired_rows=True),
                     empty_message="No expired batches \u2014 nice."),
        subtitle="Not sellable \u2014 write off to keep records accurate",
    )

    total_at_risk = sum(b.quantity_remaining for b in expiring) + sum(b.quantity_remaining for b in expired)
    header = page_header(
        "Expiry Management",
        f"{len(expiring)} batches expiring \u00b7 {len(expired)} expired \u00b7 {total_at_risk:g} units at risk",
        actions=[ft.OutlinedButton(content="Refresh", icon=ft.Icons.REFRESH, on_click=lambda e: navigate("/expiry"))],
    )

    if not expiring and not expired:
        return scroll_column([
            header,
            empty_state("Nothing expiring", "No batches are near or past their expiry date.",
                        icon=ft.Icons.EVENT_AVAILABLE_OUTLINED),
        ])

    return scroll_column([header, expiring_panel, expired_panel])


def _open_waste(page: ft.Page, navigate: Callable[[str], None], batch, product) -> None:
    app = app_context
    quantity = text_field("Quantity to write off *", value=f"{batch.quantity_remaining:g}")
    reason = text_field("Reason *", value="Expired")
    product_name = product.name if product else f"Product {batch.product_id}"

    def save(e) -> None:
        try:
            app.inventory_service.record_waste(
                batch.product_id, float((quantity.value or "").strip() or 0),
                reason=(reason.value or "").strip(), batch_id=batch.id,
            )
            page.pop_dialog()
            notify(page, "Waste recorded", "success")
            navigate("/expiry")
        except (StockWiseError, ValueError) as exc:
            notify_error(page, exc)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(f"Write off \u2014 {product_name}"),
        content=ft.Container(width=380, content=ft.Column(tight=True, spacing=T.GAP_SMALL,
                                                         controls=[quantity, reason])),
        actions=[
            ft.TextButton(content="Cancel", on_click=lambda e: page.pop_dialog()),
            ft.Button(content="Record waste", on_click=save),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.show_dialog(dialog)
