"""StockWise — CSV import/export service.

Validation always happens *before* any write. Invalid rows are reported with
their line number and field; valid rows are imported and invalid rows skipped,
so a single bad row never corrupts stock or aborts the whole file.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

from app.config import Config
from application.dto import ImportPreview, ImportResult, ImportRowError
from domain.entities import Product, ProductSupplier, Sale, SaleItem, Supplier
from domain.enums import MovementType, SaleSource
from domain.exceptions import DuplicateImportError, StockWiseError
from domain.money import to_money

PRODUCT_COLUMNS = [
    "sku", "name", "category", "unit", "brand", "cost_price", "selling_price",
    "reorder_point", "safety_stock", "expiry_tracking", "opening_stock",
    "lead_time_days", "minimum_order_qty", "pack_size", "supplier",
]

SALES_COLUMNS = ["sold_at", "sku", "quantity", "unit_price", "source", "external_ref"]

_PRODUCT_REQUIRED = ("sku", "name")
_SALES_REQUIRED = ("sku", "quantity")

_TRUE_VALUES = {"1", "true", "yes", "y", "t"}
_FALSE_VALUES = {"0", "false", "no", "n", "f", ""}


def _parse_bool(raw: str, field: str, row_no: int, errors: list[ImportRowError], default: bool = False) -> bool:
    value = (raw or "").strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    errors.append(ImportRowError(row_no, field, f"'{raw}' is not a valid yes/no value"))
    return default


def _parse_float(raw: str, field: str, row_no: int, errors: list[ImportRowError], default: float = 0.0) -> float:
    text = (raw or "").strip()
    if text == "":
        return default
    try:
        return float(text)
    except ValueError:
        errors.append(ImportRowError(row_no, field, f"'{raw}' is not a number"))
        return default


def _parse_int(raw: str, field: str, row_no: int, errors: list[ImportRowError], default: int = 0) -> int:
    text = (raw or "").strip()
    if text == "":
        return default
    try:
        return int(float(text))
    except ValueError:
        errors.append(ImportRowError(row_no, field, f"'{raw}' is not a whole number"))
        return default


class ImportExportService:
    def __init__(
        self,
        product_repo,
        sales_repo,
        product_service,
        inventory_service,
        sales_service,
        supplier_service,
        audit_repo,
    ) -> None:
        self.products = product_repo
        self.sales = sales_repo
        self.product_service = product_service
        self.inventory = inventory_service
        self.sales_service = sales_service
        self.suppliers = supplier_service
        self.audit = audit_repo

    # --------------------------------------------------------------- templates
    def template_path(self, kind: str) -> Path:
        name = "products_import_template.csv" if kind == "products" else "sales_import_template.csv"
        return Config.IMPORT_TEMPLATES_DIR / name

    def write_templates(self) -> list[Path]:
        Config.IMPORT_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        paths = []
        product_rows = [
            ["SKU-001", "Toor Dal 1kg", "Staples", "kg", "Demo Brand", "92.00", "120.00", "15", "5", "no", "40", "3", "10", "1", "Demo Distributors"],
            ["SKU-002", "Amul Taaza Milk 500ml", "Dairy", "pkt", "Amul", "25.00", "28.00", "24", "12", "yes", "60", "1", "12", "12", "Demo Dairy Supplies"],
        ]
        self._write_csv(self.template_path("products"), PRODUCT_COLUMNS, product_rows)
        paths.append(self.template_path("products"))

        sales_rows = [
            ["2026-01-01 09:30:00", "SKU-002", "2", "28.00", "csv_import", "SALE-DEMO-1"],
            ["2026-01-01 18:15:00", "SKU-001", "1", "", "csv_import", "SALE-DEMO-2"],
        ]
        self._write_csv(self.template_path("sales"), SALES_COLUMNS, sales_rows)
        paths.append(self.template_path("sales"))
        return paths

    # ---------------------------------------------------------------- exports
    def export_products(self, path: Path | str) -> Path:
        path = Path(path)
        rows = []
        for product in self.products.list_all(active_only=False):
            snapshot = self.inventory.stock_snapshot(product)
            rows.append([
                product.sku, product.name, product.category, product.unit, product.brand or "",
                f"{product.cost_price:.2f}", f"{product.selling_price:.2f}",
                str(product.reorder_point), str(product.safety_stock),
                "yes" if product.expiry_tracking else "no",
                f"{snapshot.stock_level:g}", "", "", "", "",
            ])
        columns = [c for c in PRODUCT_COLUMNS if c != "opening_stock"] + ["stock_level"]
        self._write_csv(path, columns, rows)
        return path

    def export_sales(self, path: Path | str, limit: int = 5000) -> Path:
        path = Path(path)
        rows = []
        for sale in reversed(list(self.sales.list_recent(limit=limit))):
            for item in self.sales.get_items(sale.id):
                product = self.products.get_by_id(item.product_id)
                rows.append([
                    sale.sold_at, product.sku if product else str(item.product_id),
                    f"{item.quantity:g}", f"{item.unit_price:.2f}", sale.source, sale.external_ref or "",
                ])
        self._write_csv(path, SALES_COLUMNS, rows)
        return path

    # ------------------------------------------------------------ product import
    def preview_products(self, path: Path | str) -> ImportPreview:
        rows, errors, total = self._validate_products(Path(path))
        return ImportPreview(total_rows=total, valid_rows=rows, errors=errors)

    def import_products(self, path: Path | str, actor: str = "csv_import") -> ImportResult:
        preview = self.preview_products(path)
        result = ImportResult(skipped=preview.error_count, errors=list(preview.errors))
        for row in preview.valid_rows:
            try:
                product = self.product_service.create_product(
                    Product(
                        sku=row["sku"], name=row["name"], category=row["category"],
                        unit=row["unit"], brand=row["brand"] or None,
                        cost_price=to_money(row["cost_price"]),
                        selling_price=to_money(row["selling_price"]),
                        reorder_point=row["reorder_point"], safety_stock=row["safety_stock"],
                        expiry_tracking=row["expiry_tracking"],
                    ),
                    actor=actor,
                )
                if row["opening_stock"] > 0:
                    self.inventory.receive_stock(
                        product.id, row["opening_stock"],
                        unit_cost=to_money(row["cost_price"]),
                        movement_type=MovementType.OPENING_STOCK,
                        reason="CSV product import opening stock",
                        source_type="csv_products",
                        source_id=f"row-{row['_row']}-{row['sku']}",
                        actor=actor,
                    )
                if row["supplier"]:
                    self._maybe_link_supplier(product, row, actor)
                result.imported += 1
            except StockWiseError as exc:
                result.skipped += 1
                result.errors.append(ImportRowError(row["_row"], "row", str(exc)))
        self.audit.record_event(
            "products_imported", "import", None,
            {"imported": result.imported, "skipped": result.skipped}, actor,
        )
        return result

    # -------------------------------------------------------------- sales import
    def preview_sales(self, path: Path | str) -> ImportPreview:
        rows, errors, total = self._validate_sales(Path(path))
        return ImportPreview(total_rows=total, valid_rows=rows, errors=errors)

    def import_sales(self, path: Path | str, actor: str = "csv_import") -> ImportResult:
        preview = self.preview_sales(path)
        result = ImportResult(skipped=preview.error_count, errors=list(preview.errors))
        for row in preview.valid_rows:
            product = self.product_service.get_by_sku(row["sku"])
            if product is None:
                result.skipped += 1
                result.errors.append(
                    ImportRowError(row["_row"], "sku", f"No product with SKU '{row['sku']}'")
                )
                continue
            try:
                self.sales_service.record_sale(
                    Sale(
                        sold_at=row["sold_at"] or None,
                        source=row["source"],
                        external_ref=row["external_ref"] or None,
                        items=[SaleItem(
                            product_id=product.id,
                            quantity=row["quantity"],
                            unit_price=to_money(row["unit_price"]) if row["unit_price"] else None,
                        )],
                    ),
                    actor=actor,
                )
                result.imported += 1
            except (DuplicateImportError, StockWiseError) as exc:
                result.skipped += 1
                result.errors.append(ImportRowError(row["_row"], "row", str(exc)))
        self.audit.record_event(
            "sales_imported", "import", None,
            {"imported": result.imported, "skipped": result.skipped}, actor,
        )
        return result

    # ------------------------------------------------------------------ internal
    def _validate_products(self, path: Path):
        rows: list[dict] = []
        errors: list[ImportRowError] = []
        total = 0
        seen_skus: set[str] = set()
        for row_no, raw in self._iter_csv(path, PRODUCT_COLUMNS, errors):
            total += 1
            errors_before = len(errors)
            sku = (raw.get("sku") or "").strip()
            name = (raw.get("name") or "").strip()
            if not sku:
                errors.append(ImportRowError(row_no, "sku", "SKU is required"))
            elif sku.lower() in seen_skus:
                errors.append(ImportRowError(row_no, "sku", f"Duplicate SKU '{sku}' in file"))
            if not name:
                errors.append(ImportRowError(row_no, "name", "Product name is required"))
            if sku and name:
                seen_skus.add(sku.lower())

            cost = _parse_float(raw.get("cost_price", ""), "cost_price", row_no, errors)
            price = _parse_float(raw.get("selling_price", ""), "selling_price", row_no, errors)
            if cost < 0:
                errors.append(ImportRowError(row_no, "cost_price", "Cost price cannot be negative"))
            if price < 0:
                errors.append(ImportRowError(row_no, "selling_price", "Selling price cannot be negative"))
            opening = _parse_float(raw.get("opening_stock", ""), "opening_stock", row_no, errors)
            if opening < 0:
                errors.append(ImportRowError(row_no, "opening_stock", "Opening stock cannot be negative"))

            row = {
                "_row": row_no,
                "sku": sku,
                "name": name,
                "category": (raw.get("category") or "General").strip() or "General",
                "unit": (raw.get("unit") or "pcs").strip() or "pcs",
                "brand": (raw.get("brand") or "").strip(),
                "cost_price": cost,
                "selling_price": price,
                "reorder_point": _parse_int(raw.get("reorder_point", ""), "reorder_point", row_no, errors, 10),
                "safety_stock": _parse_int(raw.get("safety_stock", ""), "safety_stock", row_no, errors, 5),
                "expiry_tracking": _parse_bool(raw.get("expiry_tracking", ""), "expiry_tracking", row_no, errors),
                "opening_stock": opening,
                "supplier": (raw.get("supplier") or "").strip(),
                "lead_time_days": _parse_int(raw.get("lead_time_days", ""), "lead_time_days", row_no, errors, 3),
                "minimum_order_qty": _parse_int(raw.get("minimum_order_qty", ""), "minimum_order_qty", row_no, errors, 1),
                "pack_size": _parse_int(raw.get("pack_size", ""), "pack_size", row_no, errors, 1),
            }
            if len(errors) == errors_before:
                rows.append(row)
        return rows, errors, total

    def _validate_sales(self, path: Path):
        rows: list[dict] = []
        errors: list[ImportRowError] = []
        total = 0
        for row_no, raw in self._iter_csv(path, SALES_COLUMNS, errors):
            total += 1
            errors_before = len(errors)
            sku = (raw.get("sku") or "").strip()
            if not sku:
                errors.append(ImportRowError(row_no, "sku", "SKU is required"))
            quantity = _parse_float(raw.get("quantity", ""), "quantity", row_no, errors)
            if quantity <= 0:
                errors.append(ImportRowError(row_no, "quantity", "Quantity must be greater than zero"))
            unit_price = _parse_float(raw.get("unit_price", ""), "unit_price", row_no, errors) if (raw.get("unit_price") or "").strip() else 0.0
            source = (raw.get("source") or SaleSource.CSV_IMPORT.value).strip() or SaleSource.CSV_IMPORT.value
            row = {
                "_row": row_no,
                "sold_at": (raw.get("sold_at") or "").strip(),
                "sku": sku,
                "quantity": quantity,
                "unit_price": unit_price,
                "source": source,
                "external_ref": (raw.get("external_ref") or "").strip(),
            }
            if len(errors) == errors_before:
                rows.append(row)
        return rows, errors, total

    def _iter_csv(self, path: Path, columns: list[str], errors: list[ImportRowError]):
        if not path.exists():
            errors.append(ImportRowError(0, "file", f"File not found: {path}"))
            return
        required = _PRODUCT_REQUIRED if columns is PRODUCT_COLUMNS else _SALES_REQUIRED
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            for col in required:
                if col not in header:
                    errors.append(ImportRowError(0, col, f"Missing required column '{col}'"))
            if errors:
                return
            for row_no, raw in enumerate(reader, start=2):  # row 1 is the header
                yield row_no, raw

    def _maybe_link_supplier(self, product: Product, row: dict, actor: str) -> None:
        name = row["supplier"]
        existing = next((s for s in self.suppliers.list_suppliers() if s.name.lower() == name.lower()), None)
        supplier = existing or self.suppliers.create_supplier(Supplier(name=name), actor=actor)
        self.suppliers.link_product_supplier(
            ProductSupplier(
                product_id=product.id,
                supplier_id=supplier.id,
                lead_time_days=row["lead_time_days"],
                minimum_order_qty=row["minimum_order_qty"],
                pack_size=row["pack_size"],
                is_preferred=True,
            ),
            actor=actor,
        )

    @staticmethod
    def _write_csv(path: Path, columns: list[str], rows: list[list]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)
