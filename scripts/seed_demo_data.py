"""Seed the StockWise database with a realistic grocery/convenience demo dataset.

Usage (from the repo root, with the project venv):

    .venv\\Scripts\\python.exe scripts\\seed_demo_data.py
    .venv\\Scripts\\python.exe scripts\\seed_demo_data.py --reset
    .venv\\Scripts\\python.exe scripts\\seed_demo_data.py --db-path C:\\temp\\demo.db

The script is idempotent: if products already exist it does nothing unless
``--reset`` is given. It never touches the real database unless pointed at it.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import build_context  # noqa: E402
from app.config import Config  # noqa: E402
from domain.entities import Product, ProductSupplier, Sale, SaleItem, Supplier  # noqa: E402
from domain.enums import MovementType  # noqa: E402
from repositories.sqlite.connection import DatabaseConnection  # noqa: E402
from repositories.sqlite.schema import initialize_database  # noqa: E402

RESET_ORDER = [
    "daily_demand", "sale_items", "sales", "stock_movements", "inventory_batches",
    "reorder_recommendations", "forecasts", "supplier_observations", "external_sources",
    "purchase_order_items", "purchase_orders", "product_suppliers", "audit_events",
    "products", "suppliers",
]

# (sku, name, category, unit, brand, cost, price, reorder, safety, expiry_days)
PRODUCTS = [
    ("AMUL-MILK-500", "Amul Taaza Milk 500ml", "Dairy", "pkt", "Amul", 25, 28, 24, 12, 4),
    ("AMUL-BUTTER-100", "Amul Butter 100g", "Dairy", "pkt", "Amul", 52, 60, 10, 5, 30),
    ("MD-CURD-400", "Mother Dairy Curd 400g", "Dairy", "cup", "Mother Dairy", 45, 55, 8, 4, 3),
    ("TOOR-DAL-1KG", "Toor Dal 1kg", "Staples", "kg", "Local Mill", 92, 120, 15, 5, None),
    ("RICE-BASMATI-5KG", "India Gate Basmati Rice 5kg", "Staples", "bag", "India Gate", 480, 560, 6, 3, None),
    ("ATTA-5KG", "Aashirvaad Atta 5kg", "Staples", "bag", "Aashirvaad", 210, 260, 8, 4, None),
    ("SUNFLOWER-OIL-1L", "Fortune Sunflower Oil 1L", "Staples", "bottle", "Fortune", 130, 155, 12, 6, None),
    ("PARLE-G-800", "Parle-G Biscuits 800g", "Snacks", "pkt", "Parle", 70, 85, 20, 10, 120),
    ("LAYS-MAGIC-52", "Lay's Magic Masala 52g", "Snacks", "pkt", "Lay's", 18, 20, 40, 20, 90),
    ("COKE-750ML", "Coca-Cola 750ml", "Beverages", "bottle", "Coca-Cola", 32, 40, 24, 12, 180),
    ("BISLERI-1L", "Bisleri Water 1L", "Beverages", "bottle", "Bisleri", 12, 20, 30, 15, None),
    ("SURF-EXCEL-1KG", "Surf Excel 1kg", "Household", "pkt", "Surf Excel", 105, 130, 10, 5, None),
    ("COLGATE-100", "Colgate Strong Teeth 100g", "Personal Care", "tube", "Colgate", 48, 60, 12, 6, None),
    ("BRIT-BROWN-BREAD", "Britannia Brown Bread", "Bakery", "loaf", "Britannia", 30, 40, 10, 5, 2),
    ("FARM-EGGS-6", "Farm Eggs (6 pcs)", "Dairy", "pack", "Local Farm", 42, 54, 10, 5, 7),
]

SUPPLIERS = [
    ("Metro Wholesale", "Ramesh", "orders@metro.example", "9800000001", "https://metro.example"),
    ("Amul Distributor - Rajesh", "Rajesh", "rajesh@amul.example", "9800000002", None),
    ("Krishna FMCG Distributors", "Krishna", "sales@krishnafmcg.example", "9800000003", "https://krishnafmcg.example"),
    ("Fresh Farm Eggs Co.", "Suresh", "suresh@freshfarm.example", "9800000004", None),
    ("City Bakery Supply", "Imran", None, "9800000005", None),
]

# sku -> list of (supplier name, supplier_sku, lead_time_days, moq, pack_size, preferred)
SUPPLIER_MAP = {
    "AMUL-MILK-500": [("Amul Distributor - Rajesh", "AM-TAAZA-500", 1, 24, 24, True), ("Metro Wholesale", None, 2, 12, 12, False)],
    "AMUL-BUTTER-100": [("Amul Distributor - Rajesh", "AM-BUT-100", 1, 10, 10, True)],
    "MD-CURD-400": [("Metro Wholesale", "MD-CURD-400", 2, 8, 8, True)],
    "TOOR-DAL-1KG": [("Metro Wholesale", "MW-DAL-TOOR", 3, 10, 1, True)],
    "RICE-BASMATI-5KG": [("Metro Wholesale", "MW-RICE-BAS-5", 3, 6, 1, True)],
    "ATTA-5KG": [("Krishna FMCG Distributors", "KD-ATTA-5", 2, 8, 1, True)],
    "SUNFLOWER-OIL-1L": [("Krishna FMCG Distributors", "KD-OIL-SUN-1", 2, 12, 12, True)],
    "PARLE-G-800": [("Krishna FMCG Distributors", "KD-PARLE-800", 2, 20, 20, True)],
    "LAYS-MAGIC-52": [("Krishna FMCG Distributors", "KD-LAYS-52", 3, 40, 40, True)],
    "COKE-750ML": [("Metro Wholesale", "MW-COKE-750", 2, 24, 24, True)],
    "BISLERI-1L": [("Metro Wholesale", "MW-BIS-1L", 2, 30, 30, True)],
    "SURF-EXCEL-1KG": [("Metro Wholesale", "MW-SURF-1", 4, 10, 10, True)],
    "COLGATE-100": [("Metro Wholesale", "MW-COL-100", 4, 12, 12, True)],
    "BRIT-BROWN-BREAD": [("City Bakery Supply", "CB-BROWN", 1, 10, 1, True)],
    "FARM-EGGS-6": [("Fresh Farm Eggs Co.", "FF-EGG-6", 1, 10, 10, True)],
}

# Opening stock levels (units). Deliberately mixes healthy, low and at-risk.
OPENING_STOCK = {
    "AMUL-MILK-500": 60, "AMUL-BUTTER-100": 14, "MD-CURD-400": 6,
    "TOOR-DAL-1KG": 40, "RICE-BASMATI-5KG": 12, "ATTA-5KG": 18,
    "SUNFLOWER-OIL-1L": 26, "PARLE-G-800": 48, "LAYS-MAGIC-52": 90,
    "COKE-750ML": 36, "BISLERI-1L": 80, "SURF-EXCEL-1KG": 9,
    "COLGATE-100": 22, "BRIT-BROWN-BREAD": 12, "FARM-EGGS-6": 20,
}


def _seed(days_of_history: int = 60) -> None:
    db = DatabaseConnection()
    initialize_database(db)
    ctx = build_context(db)

    if ctx.product_service.count_active() > 0:
        print("Database already contains products. Use --reset to reseed. Nothing to do.")
        return

    ctx.settings.set("shop_name", "Sharma General Store")
    ctx.settings.set("currency", "INR")
    ctx.settings.set("near_expiry_window_days", "7")

    # --- Suppliers ---
    supplier_by_name: dict[str, Supplier] = {}
    for name, contact, email, phone, website in SUPPLIERS:
        supplier_by_name[name] = ctx.supplier_service.create_supplier(
            Supplier(name=name, contact=contact, email=email, phone=phone, website_url=website),
            actor="seed",
        )

    # --- Products + opening stock + supplier links ---
    today = date.today()
    product_by_sku: dict[str, Product] = {}
    for sku, name, category, unit, brand, cost, price, reorder, safety, expiry_days in PRODUCTS:
        product = ctx.product_service.create_product(
            Product(
                sku=sku, name=name, category=category, unit=unit, brand=brand,
                cost_price=Decimal(str(cost)), selling_price=Decimal(str(price)),
                reorder_point=reorder, safety_stock=safety,
                expiry_tracking=expiry_days is not None,
            ),
            actor="seed",
        )
        product_by_sku[sku] = product

        expiry = (today + timedelta(days=expiry_days)).isoformat() if expiry_days is not None else None
        ctx.inventory_service.receive_stock(
            product.id, OPENING_STOCK[sku], unit_cost=Decimal(str(cost)),
            expiry_date=expiry, movement_type=MovementType.OPENING_STOCK,
            reason="Demo opening stock", source_type="seed_opening", source_id=sku, actor="seed",
        )
        for sup_name, sup_sku, lead, moq, pack, preferred in SUPPLIER_MAP.get(sku, []):
            ctx.supplier_service.link_product_supplier(
                ProductSupplier(
                    product_id=product.id, supplier_id=supplier_by_name[sup_name].id,
                    supplier_sku=sup_sku, lead_time_days=lead, minimum_order_qty=moq,
                    pack_size=pack, is_preferred=preferred,
                ),
                actor="seed",
            )

    # Add one older, now-expired batch to the dairy item so expiry handling is visible.
    ctx.inventory_service.receive_stock(
        product_by_sku["MD-CURD-400"].id, 4, unit_cost=Decimal("45"),
        expiry_date=(today - timedelta(days=1)).isoformat(),
        reason="Demo expired batch", source_type="seed_expired", source_id="MD-CURD-400",
        actor="seed",
    )

    # --- Demand history (direct writes; baseline pattern with weekend bumps) ---
    # A small share of days are simulated as "out of stock": sales were capped at
    # the little that was left, so recorded units understate true demand. That lets
    # the demand pipeline (and the model) exercise stockout-censoring handling.
    rng = random.Random(42)
    stockout_days = 0
    with db.get_connection() as conn:
        for offset in range(days_of_history, 0, -1):
            day = today - timedelta(days=offset)
            weekend = day.weekday() >= 5
            for sku, product in product_by_sku.items():
                base = max(2.0, OPENING_STOCK[sku] * 0.08)
                if weekend:
                    base *= 1.4
                quantity = round(max(0.0, base + rng.uniform(-base * 0.4, base * 0.4)), 1)
                stockout = rng.random() < 0.03
                if stockout:
                    # Shelf was empty: most demand went unserved.
                    quantity = round(quantity * rng.uniform(0.0, 0.2), 1)
                    stockout_days += 1
                conn.execute(
                    """INSERT INTO daily_demand (demand_date, product_id, quantity_sold, observed_flag, stockout_flag)
                       VALUES (?, ?, ?, 1, ?)
                       ON CONFLICT(demand_date, product_id) DO UPDATE SET
                           quantity_sold = excluded.quantity_sold,
                           stockout_flag = excluded.stockout_flag""",
                    (day.isoformat(), product.id, quantity, int(stockout)),
                )

    # --- A few real sales today (exercise the live ledger + movement feed) ---
    basket = [
        ("AMUL-MILK-500", 2), ("BRIT-BROWN-BREAD", 1), ("FARM-EGGS-6", 1),
        ("PARLE-G-800", 2), ("COKE-750ML", 2), ("BISLERI-1L", 3),
    ]
    for idx, (sku, qty) in enumerate(basket, start=1):
        ctx.sales_service.record_sale(
            Sale(
                sold_at=datetime.now().replace(microsecond=0).isoformat(sep=" "),
                source="manual", external_ref=f"DEMO-SALE-{idx}",
                items=[SaleItem(product_id=product_by_sku[sku].id, quantity=qty)],
                notes="Demo counter sale",
            ),
            actor="seed",
        )

    ctx.audit.record_event("demo_seeded", "system", None, {"days_of_history": days_of_history}, "seed")
    print(f"Seeded {len(product_by_sku)} products, {len(supplier_by_name)} suppliers, "
          f"{days_of_history} days of demand history ({stockout_days} stockout day(s)).")
    print(f"Database: {db.db_path}")


def _reset() -> None:
    db = DatabaseConnection()
    initialize_database(db)
    with db.get_connection() as conn:
        for table in RESET_ORDER:
            conn.execute(f"DELETE FROM {table}")
    print("Cleared existing demo data.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed StockWise demo data.")
    parser.add_argument("--reset", action="store_true", help="Delete existing data before seeding.")
    parser.add_argument("--days", type=int, default=60, help="Days of demand history to generate.")
    parser.add_argument("--db-path", type=str, default=None, help="Seed a specific database file.")
    args = parser.parse_args()

    if args.db_path:
        Config.DB_PATH = Path(args.db_path)

    if args.reset:
        _reset()
    _seed(days_of_history=args.days)


if __name__ == "__main__":
    main()
