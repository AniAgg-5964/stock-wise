"""StockWise — inventory service.

Owns the immutable stock ledger, batch (FEFO) consumption, and stock
adjustments. Every write happens in a single transaction via ``db``.

Hard rules enforced here:
* ``stock_movements`` is append-only — corrections are new movements.
* Expired stock is never usable and is never consumed by FEFO.
* A receipt whose ``source_type``/``source_id`` was already received is a
  duplicate and is rejected.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Sequence

from domain.entities import InventoryBatch, Product, StockMovement
from domain.enums import MovementType
from domain.exceptions import DuplicateImportError, NotFoundError, ValidationError
from domain.money import to_money
from domain.policies import StockPolicy, fefo_order, is_expired
from application.dto import ProductStock

NEAR_EXPIRY_WINDOW_DAYS = 7


class InventoryService:
    def __init__(self, db, inventory_repo, product_repo, audit_repo, supplier_service=None) -> None:
        self.db = db
        self.inventory = inventory_repo
        self.products = product_repo
        self.audit = audit_repo
        self.supplier_service = supplier_service

    # ------------------------------------------------------------------ writes
    def receive_stock(
        self,
        product_id: int,
        quantity: float,
        *,
        unit_cost=None,
        expiry_date: str | None = None,
        batch_code: str | None = None,
        movement_type: MovementType | str = MovementType.PURCHASE_RECEIPT,
        reason: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        actor: str = "system",
    ) -> StockMovement:
        """Receive stock: create a batch and append one ledger movement (atomic)."""
        StockPolicy.validate_positive(quantity, "quantity")
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)

        with self.db.get_connection() as conn:
            if source_type and source_id and self.inventory.movement_exists(
                source_type, source_id, conn=conn
            ):
                raise DuplicateImportError(f"{source_type}:{source_id}")

            self.inventory.create_batch(
                InventoryBatch(
                    product_id=product_id,
                    batch_code=batch_code,
                    expiry_date=expiry_date,
                    quantity_received=quantity,
                    quantity_remaining=quantity,
                    unit_cost=to_money(unit_cost) if unit_cost is not None else None,
                ),
                conn=conn,
            )

            balance = self.inventory.stock_level(product_id, conn=conn) + quantity
            movement = self.inventory.add_movement(
                StockMovement(
                    product_id=product_id,
                    movement_type=movement_type,
                    quantity_delta=quantity,
                    balance_after=balance,
                    reason=reason,
                    source_type=source_type,
                    source_id=str(source_id) if source_id is not None else None,
                    created_by=actor,
                ),
                conn=conn,
            )
            self.audit.record_event(
                "stock_received", "product", product_id,
                {"quantity": quantity, "type": str(getattr(movement_type, "value", movement_type))},
                actor, conn=conn,
            )
        return movement

    def adjust_stock(
        self,
        product_id: int,
        quantity_delta: float,
        *,
        reason: str,
        movement_type: MovementType | str = MovementType.ADJUSTMENT,
        actor: str = "system",
    ) -> StockMovement:
        """Apply a signed manual adjustment (never rewrites history)."""
        if quantity_delta == 0:
            raise ValidationError("quantity_delta", "Adjustment cannot be zero")
        if not reason or not reason.strip():
            raise ValidationError("reason", "A reason is required for adjustments")
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)

        with self.db.get_connection() as conn:
            if quantity_delta > 0:
                self.inventory.create_batch(
                    InventoryBatch(
                        product_id=product_id,
                        batch_code="ADJUST",
                        quantity_received=quantity_delta,
                        quantity_remaining=quantity_delta,
                        unit_cost=product.cost_price,
                    ),
                    conn=conn,
                )
            else:
                self.consume_fefo(product_id, abs(quantity_delta), conn=conn)

            balance = self.inventory.stock_level(product_id, conn=conn) + quantity_delta
            movement = self.inventory.add_movement(
                StockMovement(
                    product_id=product_id,
                    movement_type=movement_type,
                    quantity_delta=quantity_delta,
                    balance_after=balance,
                    reason=reason,
                    source_type="adjustment",
                    created_by=actor,
                ),
                conn=conn,
            )
            self.audit.record_event(
                "stock_adjusted", "product", product_id,
                {"delta": quantity_delta, "reason": reason}, actor, conn=conn,
            )
        return movement

    def record_waste(
        self,
        product_id: int,
        quantity: float,
        *,
        reason: str,
        batch_id: int | None = None,
        actor: str = "system",
    ) -> StockMovement:
        """Write off stock (e.g. spoilage/expiry) as a WASTE movement."""
        StockPolicy.validate_positive(quantity, "quantity")
        if not reason or not reason.strip():
            raise ValidationError("reason", "A reason is required when recording waste")
        product = self.products.get_by_id(product_id)
        if product is None:
            raise NotFoundError("Product", product_id)

        with self.db.get_connection() as conn:
            if batch_id is not None:
                batch = self.inventory.get_batch(batch_id, conn=conn)
                if batch is None:
                    raise NotFoundError("Batch", batch_id)
                take = min(batch.quantity_remaining, quantity)
                self.inventory.update_batch_remaining(
                    batch_id, batch.quantity_remaining - take, conn=conn
                )
            else:
                self.consume_fefo(product_id, quantity, conn=conn)

            balance = self.inventory.stock_level(product_id, conn=conn) - quantity
            movement = self.inventory.add_movement(
                StockMovement(
                    product_id=product_id,
                    batch_id=batch_id,
                    movement_type=MovementType.WASTE,
                    quantity_delta=-quantity,
                    balance_after=balance,
                    reason=reason,
                    source_type="waste",
                    created_by=actor,
                ),
                conn=conn,
            )
            self.audit.record_event(
                "stock_wasted", "product", product_id,
                {"quantity": quantity, "reason": reason}, actor, conn=conn,
            )
        return movement

    def consume_fefo(
        self, product_id: int, quantity: float, *, as_of: str | None = None, conn=None
    ) -> float:
        """Consume ``quantity`` from the earliest-expiring usable batches.

        Returns the amount actually consumed from batches (which can be less
        than requested only when an override sale is allowed).
        """
        batches = self.inventory.get_batches_for_product(product_id, conn=conn)
        remaining = float(quantity)
        consumed = 0.0
        for batch in fefo_order(list(batches), as_of=as_of):
            if remaining <= 0:
                break
            take = min(batch.quantity_remaining, remaining)
            self.inventory.update_batch_remaining(
                batch.id, batch.quantity_remaining - take, conn=conn
            )
            remaining -= take
            consumed += take
        return consumed

    # ------------------------------------------------------------------- reads
    def stock_level(self, product_id: int, *, conn=None) -> float:
        """Ledger balance (physical units, including expired stock)."""
        return self.inventory.stock_level(product_id, conn=conn)

    def usable_stock(self, product_id: int, *, as_of: str | None = None, conn=None) -> float:
        """Non-expired, in-batch units (what can actually be sold)."""
        return self.inventory.usable_stock(product_id, as_of=as_of, conn=conn)

    def get_stock_level(self, product_id: int) -> float:
        return self.stock_level(product_id)

    def get_usable_stock(self, product_id: int, as_of: str | None = None) -> float:
        return self.usable_stock(product_id, as_of=as_of)

    def get_batches(self, product_id: int, *, include_depleted: bool = False) -> Sequence[InventoryBatch]:
        return self.inventory.get_batches_for_product(product_id, include_depleted=include_depleted)

    def get_movements(self, product_id: int | None = None, limit: int = 100) -> Sequence[StockMovement]:
        return self.inventory.get_stock_movements(product_id=product_id, limit=limit)

    def total_stock_value(self):
        return self.inventory.total_stock_value()

    def expiring_batches(self, days: int = NEAR_EXPIRY_WINDOW_DAYS):
        return self.inventory.batches_expiring_within(days)

    def expired_batches(self):
        return self.inventory.expired_batches()

    def stock_snapshot(self, product: Product, as_of: str | None = None) -> ProductStock:
        """Compute the live stock snapshot for one product."""
        reference = as_of or date.today().isoformat()
        batches = list(self.inventory.get_batches_for_product(product.id, include_depleted=True))
        live = [b for b in batches if b.quantity_remaining > 0]
        usable = sum(b.quantity_remaining for b in live if not is_expired(b, reference))
        ledger = self.inventory.stock_level(product.id)

        near = any(
            b.expiry_date and reference <= b.expiry_date <= _plus_days(NEAR_EXPIRY_WINDOW_DAYS)
            for b in live
        )
        expired_present = any(is_expired(b, reference) for b in live)

        status = StockPolicy.derive_status(
            usable, product.reorder_point, near_expiry=near, expired_present=expired_present
        )
        expiry_dates = sorted(b.expiry_date for b in live if b.expiry_date)
        return ProductStock(
            product=product,
            stock_level=ledger,
            usable_stock=usable,
            status=status.value,
            batch_count=len(live),
            nearest_expiry=expiry_dates[0] if expiry_dates else None,
        )

    def snapshots_for_products(self, products: Sequence[Product]) -> list[ProductStock]:
        return [self.stock_snapshot(p) for p in products]


def _plus_days(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()
