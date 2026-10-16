"""Acceptance test — CSV import reports row-level errors without corrupting stock."""

from __future__ import annotations

from decimal import Decimal

from application.services.import_export_service import PRODUCT_COLUMNS, SALES_COLUMNS


def _write(path, columns, rows):
    lines = [",".join(columns).rstrip(",")]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_product_import_reports_row_errors_and_only_imports_valid_rows(ctx, tmp_path):
    path = tmp_path / "products.csv"
    _write(path, PRODUCT_COLUMNS, [
        ["SKU-OK", "Good Product", "Staples", "kg", "", "10", "15", "5", "2", "no", "20", "", "", "", ""],
        ["SKU-NONAME", "", "Staples", "kg", "", "10", "15", "5", "2", "no", "5", "", "", "", ""],
        ["SKU-NEG", "Negative Stock", "Staples", "kg", "", "10", "15", "5", "2", "no", "-3", "", "", "", ""],
        ["SKU-BADPRICE", "Bad Price", "Staples", "kg", "", "abc", "15", "5", "2", "no", "1", "", "", "", ""],
    ])

    preview = ctx.import_export_service.preview_products(path)
    assert preview.total_rows == 4
    assert preview.valid_count == 1
    assert preview.error_count == 3
    assert all(e.row_number >= 2 for e in preview.errors)

    result = ctx.import_export_service.import_products(path)
    assert result.imported == 1
    assert result.skipped == 3

    ok = ctx.product_service.get_by_sku("SKU-OK")
    assert ok is not None
    assert ctx.inventory_service.stock_level(ok.id) == 20
    for bad_sku in ("SKU-NONAME", "SKU-NEG", "SKU-BADPRICE"):
        assert ctx.product_service.get_by_sku(bad_sku) is None


def test_sales_import_skips_unknown_sku_and_duplicates(ctx, tmp_path):
    from domain.entities import Product
    from domain.enums import MovementType

    product = ctx.product_service.create_product(
        Product(sku="MILK", name="Milk", cost_price=Decimal("25"), selling_price=Decimal("28"))
    )
    ctx.inventory_service.receive_stock(product.id, 20, movement_type=MovementType.OPENING_STOCK)

    path = tmp_path / "sales.csv"
    _write(path, SALES_COLUMNS, [
        ["2026-01-05 09:00:00", "MILK", "3", "28", "csv_import", "INV-A"],
        ["2026-01-05 10:00:00", "UNKNOWN", "1", "5", "csv_import", "INV-B"],
        ["2026-01-05 11:00:00", "MILK", "2", "28", "csv_import", "INV-A"],
        ["2026-01-05 12:00:00", "MILK", "999", "28", "csv_import", "INV-C"],
    ])

    result = ctx.import_export_service.import_sales(path)

    assert result.imported == 1
    assert result.skipped == 3
    # 20 opening - 3 sold = 17; the oversell and duplicate rows must not have applied.
    assert ctx.inventory_service.stock_level(product.id) == 17
    assert ctx.sales_repo.find_by_external_ref("csv_import", "INV-A") is not None
    assert ctx.sales_repo.find_by_external_ref("csv_import", "INV-C") is None


def test_export_round_trips_products(ctx, tmp_path):
    from domain.entities import Product
    from domain.enums import MovementType

    product = ctx.product_service.create_product(
        Product(sku="RICE", name="Rice", selling_price=Decimal("55"))
    )
    ctx.inventory_service.receive_stock(product.id, 7, movement_type=MovementType.OPENING_STOCK)

    out = ctx.import_export_service.export_products(tmp_path / "products_out.csv")
    text = out.read_text(encoding="utf-8-sig")
    assert "RICE" in text
    assert "7" in text
