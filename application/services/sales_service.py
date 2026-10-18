"""StockWise — sales service.

Recording a sale and its stock movements happens in ONE transaction. If
anything fails, neither the sale nor the stock ledger records survive.

Overselling is blocked by default; an explicit override allows a negative
balance and is audited.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from domain.entities import Sale, SaleItem, StockMovement
from domain.enums import MovementType
from domain.exceptions import (
    DuplicateImportError,
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)
from domain.money import to_money
from domain.policies import StockPolicy


class SalesService:
    def __init__(self, db, sales_repo, product_repo, inventory_service, audit_repo,
                 forecast_service=None) -> None:
        self.db = db
        self.sales = sales_repo
        self.products = product_repo
        self.inventory = inventory_service
        self.audit = audit_repo
        # Optional: lets a recorded sale drop the forecast service's memoised
        # demand reads, so forecasts and reorder figures never lag a real sale.
        self.forecasts = forecast_service

    # ------------------------------------------------------------------ writes
    def record_sale(self, sale: Sale, *, allow_override: bool = False, actor: str = "system") -> Sale:
        """Record a sale atomically (sale header + items + stock movements)."""
        if not sale.items:
            raise ValidationError("items", "A sale must contain at least one item")
        if sale.source is None:
            sale.source = "manual"

        # Idempotency guard: same source+external_ref must not be imported twice.
        if sale.external_ref and sale.source:
            existing = self.sales.find_by_external_ref(sale.source, sale.external_ref)
            if existing is not None:
                raise DuplicateImportError(f"{sale.source}:{sale.external_ref}")

        # Validate items and compute totals before touching the database.
        total = Decimal("0")
        overridden: list[dict] = []
        for item in sale.items:
            StockPolicy.validate_positive(item.quantity, "quantity")
            product = self.products.get_by_id(item.product_id)
            if product is None:
                raise NotFoundError("Product", item.product_id)
            if item.unit_price is None or to_money(item.unit_price) == 0:
                item.unit_price = product.selling_price
            item.unit_price = to_money(item.unit_price)
            item.line_total = to_money(item.unit_price * Decimal(str(item.quantity)))
            total += item.line_total
        sale.total_amount = to_money(total)

        demand_date = (sale.sold_at or datetime.now().isoformat(sep=" "))[:10]
        demand_by_product: dict[int, float] = {}

        # ----- single transaction -----
        with self.db.get_connection() as conn:
            header = self.sales.create_sale_header(sale, conn=conn)

            for item in sale.items:
                product = self.products.get_by_id(item.product_id, conn=conn)
                usable = self.inventory.usable_stock(item.product_id, conn=conn)

                if usable < item.quantity and not allow_override:
                    raise InsufficientStockError(
                        item.quantity, usable,
                        f"Insufficient usable stock for '{product.name}': "
                        f"requested {item.quantity}, available {usable}",
                    )

                if usable < item.quantity:
                    overridden.append({
                        "product_id": item.product_id,
                        "name": product.name,
                        "requested": item.quantity,
                        "available": usable,
                    })

                item.sale_id = header.id
                item.unit_cost_snapshot = product.cost_price

                # Consume physical batches FEFO (never expired) and append ledger entry.
                self.inventory.consume_fefo(item.product_id, item.quantity, conn=conn)
                new_balance = self.inventory.stock_level(item.product_id, conn=conn) - item.quantity
                self.sales.add_item(item, conn=conn)
                self.inventory.inventory.add_movement(
                    StockMovement(
                        product_id=item.product_id,
                        movement_type=MovementType.SALE,
                        quantity_delta=-item.quantity,
                        balance_after=new_balance,
                        reason=f"Sale #{header.id}",
                        source_type=sale.source,
                        source_id=str(header.id),
                        created_by=actor,
                    ),
                    conn=conn,
                )
                demand_by_product[item.product_id] = (
                    demand_by_product.get(item.product_id, 0.0) + item.quantity
                )

            for product_id, quantity in demand_by_product.items():
                self.sales.record_daily_demand(
                    product_id, demand_date, quantity, conn=conn
                )

            self.audit.record_event(
                "sale_recorded", "sale", header.id,
                {"items": len(sale.items), "total": str(sale.total_amount)},
                actor, conn=conn,
            )
            if overridden:
                self.audit.record_event(
                    "sale_override", "sale", header.id, {"overridden": overridden}, actor, conn=conn,
                )

        sale.id = header.id
        sale.created_at = header.created_at

        # Committed, so now the memoised demand reads for the affected products
        # are stale: drop them or the next forecast/alerts view shows pre-sale
        # numbers. Done after the transaction so a rollback cannot clear a cache
        # that was still valid.
        if self.forecasts is not None:
            for product_id in demand_by_product:
                self.forecasts.invalidate_demand_cache(product_id)
        return sale

    # ------------------------------------------------------------------- reads
    def get_sale(self, sale_id: int) -> Sale | None:
        return self.sales.get_sale(sale_id)

    def list_recent(self, limit: int = 50) -> Sequence[Sale]:
        return self.sales.list_recent(limit)

    def get_items(self, sale_id: int) -> Sequence[SaleItem]:
        return self.sales.get_items(sale_id)
