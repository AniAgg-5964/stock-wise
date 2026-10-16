"""StockWise — product service.

Owns product CRUD and validation. Audits every create/update/archive.
"""

from __future__ import annotations

from typing import Sequence

from domain.entities import Product
from domain.exceptions import NotFoundError, ValidationError
from domain.money import to_money
from domain.policies import StockPolicy


class ProductService:
    def __init__(self, product_repo, audit_repo) -> None:
        self.products = product_repo
        self.audit = audit_repo

    # --- Writes ---
    def create_product(self, product: Product, actor: str = "system") -> Product:
        product.sku = (product.sku or "").strip()
        product.name = (product.name or "").strip()
        product.cost_price = to_money(product.cost_price)
        product.selling_price = to_money(product.selling_price)
        StockPolicy.validate_product_data(product)
        if self.products.get_by_sku(product.sku):
            raise ValidationError("sku", f"A product with SKU '{product.sku}' already exists")

        created = self.products.create(product)
        self.audit.record_event(
            "product_created", "product", created.id,
            {"sku": created.sku, "name": created.name}, actor,
        )
        return created

    def update_product(self, product: Product, actor: str = "system") -> Product:
        if product.id is None:
            raise ValidationError("id", "Cannot update a product without an id")
        existing = self.products.get_by_id(product.id)
        if existing is None:
            raise NotFoundError("Product", product.id)

        product.sku = (product.sku or "").strip()
        product.name = (product.name or "").strip()
        product.cost_price = to_money(product.cost_price)
        product.selling_price = to_money(product.selling_price)
        StockPolicy.validate_product_data(product)

        duplicate = self.products.get_by_sku(product.sku)
        if duplicate and duplicate.id != product.id:
            raise ValidationError("sku", f"A product with SKU '{product.sku}' already exists")

        updated = self.products.update(product)
        self.audit.record_event(
            "product_updated", "product", updated.id,
            {"sku": updated.sku, "name": updated.name}, actor,
        )
        return updated

    def archive_product(self, product_id: int, actor: str = "system") -> None:
        if self.products.get_by_id(product_id) is None:
            raise NotFoundError("Product", product_id)
        self.products.archive(product_id)
        self.audit.record_event("product_archived", "product", product_id, {}, actor)

    # --- Reads ---
    def get_product(self, product_id: int) -> Product | None:
        return self.products.get_by_id(product_id)

    def get_by_sku(self, sku: str) -> Product | None:
        return self.products.get_by_sku(sku)

    def list_products(
        self,
        *,
        active_only: bool = True,
        category: str | None = None,
        search_query: str | None = None,
    ) -> Sequence[Product]:
        return self.products.list_all(
            active_only=active_only, category=category, search_query=search_query
        )

    def list_categories(self) -> list[str]:
        categories = {p.category for p in self.products.list_all(active_only=True) if p.category}
        return sorted(categories, key=str.lower)

    def count_active(self) -> int:
        return self.products.count(active_only=True)
