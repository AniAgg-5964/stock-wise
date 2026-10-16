"""StockWise — Supplier research view (P0 subset: directory + product mapping).

TinyFish-powered web research is a later stage; this screen manages the local
supplier directory and the product↔supplier links used by reordering.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.theme import StockWiseTheme as T
from domain.entities import ProductSupplier, Supplier
from domain.exceptions import StockWiseError
from ui.components.empty_state import empty_state
from ui.components.feedback import notify, notify_error
from ui.components.forms import dropdown_field, text_field
from ui.components.layout import page_header, panel_grid, scroll_column, section
from ui.components.table import action_cell, chip_cell, styled_table, text_cell


def build_suppliers_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    suppliers = list(app.supplier_service.list_suppliers())
    products = list(app.product_service.list_products(active_only=True))

    header = page_header(
        "Supplier Research",
        "Directory of suppliers and how products are sourced",
        actions=[ft.Button(content="Add supplier", icon=ft.Icons.ADD,
                           on_click=lambda e: _open_add_supplier(page, navigate))],
    )

    supplier_rows = [
        ft.DataRow(cells=[
            text_cell(s.name),
            text_cell(s.contact or "\u2014", color=T.TEXT_SECONDARY),
            text_cell(s.phone or "\u2014", color=T.TEXT_SECONDARY),
            text_cell(s.email or "\u2014", color=T.TEXT_SECONDARY),
            chip_cell("Active", "healthy") if s.active else chip_cell("Archived", "neutral"),
            action_cell(lambda e, sid=s.id: _open_edit_supplier(page, navigate, sid), icon=ft.Icons.EDIT_OUTLINED,
                        tooltip="Edit supplier"),
        ])
        for s in suppliers
    ]
    supplier_panel = section(
        "Supplier directory",
        styled_table(["Name", "Contact", "Phone", "Email", "Status", ""], supplier_rows,
                     empty_message="No suppliers yet. Add your first supplier."),
    )

    # --- Sourcing map ---
    sourcing_rows = []
    for product in products:
        preferred = app.supplier_service.get_preferred_supplier(product.id)
        if preferred is None:
            sourcing_rows.append(ft.DataRow(cells=[
                text_cell(product.name),
                text_cell("\u2014", color=T.TEXT_TERTIARY),
                text_cell("\u2014", color=T.TEXT_TERTIARY),
                text_cell("\u2014", color=T.TEXT_TERTIARY),
                text_cell("\u2014", color=T.TEXT_TERTIARY),
                chip_cell("Not sourced", "warning"),
            ]))
            continue
        link, supplier = preferred
        sourcing_rows.append(ft.DataRow(cells=[
            text_cell(product.name),
            text_cell(supplier.name),
            text_cell(f"{link.lead_time_days} d", color=T.TEXT_SECONDARY),
            text_cell(str(link.minimum_order_qty), color=T.TEXT_SECONDARY),
            text_cell(str(link.pack_size), color=T.TEXT_SECONDARY),
            chip_cell("Preferred", "healthy") if link.is_preferred else chip_cell("Backup", "neutral"),
        ]))
    sourcing_panel = section(
        "Product sourcing",
        styled_table(["Product", "Supplier", "Lead time", "MOQ", "Pack", "Role"], sourcing_rows,
                     empty_message="Add products to map their suppliers."),
        subtitle="Used by reorder recommendations (advisory only)",
    )

    link_panel = _build_link_panel(page, navigate, products, suppliers)

    return scroll_column([
        header,
        supplier_panel,
        panel_grid([(sourcing_panel, 7), (link_panel, 5)]),
    ])


def _build_link_panel(page: ft.Page, navigate: Callable[[str], None], products, suppliers) -> ft.Control:
    app = app_context
    if not products or not suppliers:
        return section(
            "Link a product to a supplier",
            empty_state("Not enough data", "Add at least one product and one supplier first."),
            expand=True,
        )

    product_dd = dropdown_field("Product", [(str(p.id), p.name) for p in products], value=str(products[0].id))
    supplier_dd = dropdown_field("Supplier", [(str(s.id), s.name) for s in suppliers], value=str(suppliers[0].id))
    lead = text_field("Lead time (days)", value="3")
    moq = text_field("Minimum order qty", value="1")
    pack = text_field("Pack size", value="1")
    cost = text_field("Unit cost (optional)")
    preferred = ft.Switch(label="Preferred supplier", value=True,
                          label_text_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL))

    def link(e) -> None:
        try:
            app.supplier_service.link_product_supplier(ProductSupplier(
                product_id=int(product_dd.value), supplier_id=int(supplier_dd.value),
                lead_time_days=int(float(lead.value or 3)), minimum_order_qty=int(float(moq.value or 1)),
                pack_size=int(float(pack.value or 1)),
                unit_cost=Decimal(cost.value) if (cost.value or "").strip() else None,
                is_preferred=bool(preferred.value),
            ))
            notify(page, "Product linked to supplier", "success")
            navigate("/suppliers")
        except (StockWiseError, ValueError, InvalidOperation) as exc:
            notify_error(page, exc)

    return section(
        "Link a product to a supplier",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            product_dd, supplier_dd, lead, moq, pack, cost, preferred,
            ft.Button(content="Link product", icon=ft.Icons.LINK, on_click=link),
        ]),
        expand=True,
    )


def _open_add_supplier(page: ft.Page, navigate: Callable[[str], None]) -> None:
    app = app_context
    fields = {
        "name": text_field("Supplier name *", autofocus=True),
        "contact": text_field("Contact person"),
        "phone": text_field("Phone"),
        "email": text_field("Email"),
        "website": text_field("Website"),
        "address": text_field("Address", multiline=True),
        "notes": text_field("Notes", multiline=True),
    }

    def save(e) -> None:
        try:
            app.supplier_service.create_supplier(Supplier(
                name=fields["name"].value,
                contact=(fields["contact"].value or "").strip() or None,
                phone=(fields["phone"].value or "").strip() or None,
                email=(fields["email"].value or "").strip() or None,
                website_url=(fields["website"].value or "").strip() or None,
                address=(fields["address"].value or "").strip() or None,
                notes=(fields["notes"].value or "").strip() or None,
            ))
            page.pop_dialog()
            notify(page, "Supplier added", "success")
            navigate("/suppliers")
        except StockWiseError as exc:
            notify_error(page, exc)

    _show_supplier_dialog(page, "Add supplier", list(fields.values()), save)


def _open_edit_supplier(page: ft.Page, navigate: Callable[[str], None], supplier_id: int) -> None:
    app = app_context
    supplier = app.supplier_service.get_supplier(supplier_id)
    if supplier is None:
        return
    fields = {
        "name": text_field("Supplier name *", value=supplier.name, autofocus=True),
        "contact": text_field("Contact person", value=supplier.contact or ""),
        "phone": text_field("Phone", value=supplier.phone or ""),
        "email": text_field("Email", value=supplier.email or ""),
        "website": text_field("Website", value=supplier.website_url or ""),
        "address": text_field("Address", value=supplier.address or "", multiline=True),
        "notes": text_field("Notes", value=supplier.notes or "", multiline=True),
    }
    active = ft.Switch(label="Active", value=supplier.active,
                       label_text_style=ft.TextStyle(color=T.TEXT_SECONDARY, size=T.FONT_SMALL))

    def save(e) -> None:
        try:
            app.supplier_service.update_supplier(Supplier(
                id=supplier.id, name=fields["name"].value,
                contact=(fields["contact"].value or "").strip() or None,
                phone=(fields["phone"].value or "").strip() or None,
                email=(fields["email"].value or "").strip() or None,
                website_url=(fields["website"].value or "").strip() or None,
                address=(fields["address"].value or "").strip() or None,
                notes=(fields["notes"].value or "").strip() or None,
                active=bool(active.value),
            ))
            page.pop_dialog()
            notify(page, "Supplier updated", "success")
            navigate("/suppliers")
        except StockWiseError as exc:
            notify_error(page, exc)

    _show_supplier_dialog(page, "Edit supplier", list(fields.values()) + [active], save)


def _show_supplier_dialog(page: ft.Page, title: str, controls: list[ft.Control], on_save: Callable) -> None:
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
