"""StockWise — Reports & data view (CSV import/export).

Import always validates first and shows row-level errors. Only valid rows are
committed, so one bad row never corrupts stock or aborts the file.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import flet as ft

from app.bootstrap import app_context
from app.config import Config
from app.theme import StockWiseTheme as T
from ui.components.feedback import banner, notify, notify_error
from ui.components.forms import text_field
from ui.components.layout import page_header, scroll_column, section
from ui.components.table import styled_table, text_cell

IMPORT_DIR = Config.APP_DATA_DIR / "imports"
EXPORT_DIR = Config.APP_DATA_DIR / "exports"


def build_import_export_view(page: ft.Page, navigate: Callable[[str], None]) -> ft.Control:
    app = app_context
    app.import_export_service.write_templates()  # ensure templates exist on disk

    products_path = text_field("Products CSV file", value=str(IMPORT_DIR / "products.csv"), expand=True)
    sales_path = text_field("Sales CSV file", value=str(IMPORT_DIR / "sales.csv"), expand=True)
    products_preview = ft.Column(spacing=T.GAP_SMALL)
    sales_preview = ft.Column(spacing=T.GAP_SMALL)

    def download_template(kind: str, target: str) -> None:
        try:
            source = app.import_export_service.template_path(kind)
            destination = Path(target)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            notify(page, f"Template saved to {destination}", "success")
        except Exception as exc:  # pragma: no cover - filesystem
            notify_error(page, exc)

    def render_preview(holder: ft.Column, preview) -> None:
        if preview.total_rows == 0 and preview.error_count == 0:
            holder.controls = [banner("The file has no data rows.", "warning")]
            return
        kind = "success" if not preview.has_errors else "warning"
        holder.controls = [
            banner(
                f"{preview.valid_count} valid row(s), {preview.error_count} row(s) with errors "
                f"out of {preview.total_rows}.",
                kind,
            )
        ]
        if preview.has_errors:
            rows = [ft.DataRow(cells=[
                text_cell(str(err.row_number)),
                text_cell(err.field),
                text_cell(err.message, color=T.STATUS_CRITICAL),
            ]) for err in preview.errors[:50]]
            holder.controls.append(styled_table(["Row", "Field", "Problem"], rows))

    def preview_products(e) -> None:
        render_preview(products_preview, app.import_export_service.preview_products(products_path.value))

    def import_products(e) -> None:
        result = app.import_export_service.import_products(products_path.value)
        render_preview(products_preview, app.import_export_service.preview_products(products_path.value))
        notify(page, f"Imported {result.imported}, skipped {result.skipped}", "success" if not result.errors else "warning")

    def preview_sales(e) -> None:
        render_preview(sales_preview, app.import_export_service.preview_sales(sales_path.value))

    def import_sales(e) -> None:
        result = app.import_export_service.import_sales(sales_path.value)
        render_preview(sales_preview, app.import_export_service.preview_sales(sales_path.value))
        notify(page, f"Imported {result.imported}, skipped {result.skipped}", "success" if not result.errors else "warning")

    def export_products(e) -> None:
        try:
            target = EXPORT_DIR / "products_export.csv"
            app.import_export_service.export_products(target)
            notify(page, f"Exported products to {target}", "success")
        except Exception as exc:  # pragma: no cover
            notify_error(page, exc)

    def export_sales(e) -> None:
        try:
            target = EXPORT_DIR / "sales_export.csv"
            app.import_export_service.export_sales(target)
            notify(page, f"Exported sales to {target}", "success")
        except Exception as exc:  # pragma: no cover
            notify_error(page, exc)

    products_panel = section(
        "Import products",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            ft.Row(spacing=T.GAP_SMALL, controls=[
                products_path,
                ft.OutlinedButton(content="Download template", icon=ft.Icons.DOWNLOAD,
                                  on_click=lambda e: download_template("products", products_path.value)),
            ]),
            ft.Row(spacing=T.GAP_SMALL, controls=[
                ft.OutlinedButton(content="Validate", icon=ft.Icons.FACT_CHECK_OUTLINED, on_click=preview_products),
                ft.Button(content="Import valid rows", icon=ft.Icons.UPLOAD, on_click=import_products),
            ]),
            products_preview,
        ]),
        subtitle="Columns: sku, name, category, unit, brand, cost_price, selling_price, reorder_point, safety_stock, expiry_tracking, opening_stock, supplier \u2026",
    )

    sales_panel = section(
        "Import sales",
        ft.Column(spacing=T.GAP_SMALL, controls=[
            ft.Row(spacing=T.GAP_SMALL, controls=[
                sales_path,
                ft.OutlinedButton(content="Download template", icon=ft.Icons.DOWNLOAD,
                                  on_click=lambda e: download_template("sales", sales_path.value)),
            ]),
            ft.Row(spacing=T.GAP_SMALL, controls=[
                ft.OutlinedButton(content="Validate", icon=ft.Icons.FACT_CHECK_OUTLINED, on_click=preview_sales),
                ft.Button(content="Import valid rows", icon=ft.Icons.UPLOAD, on_click=import_sales),
            ]),
            sales_preview,
        ]),
        subtitle="Columns: sold_at, sku, quantity, unit_price, source, external_ref \u00b7 duplicates and oversells are skipped",
    )

    export_panel = section(
        "Export data",
        ft.Row(spacing=T.GAP_SMALL, wrap=True, controls=[
            ft.OutlinedButton(content="Export products CSV", icon=ft.Icons.TABLE_VIEW,
                              on_click=export_products),
            ft.OutlinedButton(content="Export sales CSV", icon=ft.Icons.RECEIPT_LONG,
                              on_click=export_sales),
        ]),
        subtitle=f"Files are written to {EXPORT_DIR}",
    )

    return scroll_column([
        page_header("Reports & Data", "Import and export CSV data"),
        products_panel,
        sales_panel,
        export_panel,
    ])
