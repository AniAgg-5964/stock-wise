"""StockWise — supplier service.

Owns supplier CRUD and the product↔supplier mapping (used later by reorder and
supplier research). All writes are audited.
"""

from __future__ import annotations

from typing import Sequence

from domain.entities import ProductSupplier, Supplier
from domain.exceptions import NotFoundError, ValidationError


class SupplierService:
    def __init__(self, supplier_repo, product_repo, audit_repo) -> None:
        self.suppliers = supplier_repo
        self.products = product_repo
        self.audit = audit_repo

    # --- Writes ---
    def create_supplier(self, supplier: Supplier, actor: str = "system") -> Supplier:
        supplier.name = (supplier.name or "").strip()
        if not supplier.name:
            raise ValidationError("name", "Supplier name is required")
        created = self.suppliers.create(supplier)
        self.audit.record_event(
            "supplier_created", "supplier", created.id, {"name": created.name}, actor
        )
        return created

    def update_supplier(self, supplier: Supplier, actor: str = "system") -> Supplier:
        if supplier.id is None:
            raise ValidationError("id", "Cannot update a supplier without an id")
        if self.suppliers.get_by_id(supplier.id) is None:
            raise NotFoundError("Supplier", supplier.id)
        supplier.name = (supplier.name or "").strip()
        if not supplier.name:
            raise ValidationError("name", "Supplier name is required")
        updated = self.suppliers.update(supplier)
        self.audit.record_event(
            "supplier_updated", "supplier", updated.id, {"name": updated.name}, actor
        )
        return updated

    def archive_supplier(self, supplier_id: int, actor: str = "system") -> None:
        if self.suppliers.get_by_id(supplier_id) is None:
            raise NotFoundError("Supplier", supplier_id)
        self.suppliers.archive(supplier_id)
        self.audit.record_event("supplier_archived", "supplier", supplier_id, {}, actor)

    def link_product_supplier(self, link: ProductSupplier, actor: str = "system") -> ProductSupplier:
        if self.products.get_by_id(link.product_id) is None:
            raise NotFoundError("Product", link.product_id)
        if self.suppliers.get_by_id(link.supplier_id) is None:
            raise NotFoundError("Supplier", link.supplier_id)
        if link.lead_time_days < 0:
            raise ValidationError("lead_time_days", "Lead time cannot be negative")
        if link.minimum_order_qty < 1:
            raise ValidationError("minimum_order_qty", "Minimum order quantity must be at least 1")
        if link.pack_size < 1:
            raise ValidationError("pack_size", "Pack size must be at least 1")

        saved = self.suppliers.link_product_supplier(link)
        self.audit.record_event(
            "product_supplier_linked", "product", link.product_id,
            {"supplier_id": link.supplier_id, "preferred": link.is_preferred}, actor,
        )
        return saved

    # --- Reads ---
    def get_supplier(self, supplier_id: int) -> Supplier | None:
        return self.suppliers.get_by_id(supplier_id)

    def list_suppliers(self, *, active_only: bool = True) -> Sequence[Supplier]:
        return self.suppliers.list_all(active_only=active_only)

    def get_product_suppliers(self, product_id: int) -> Sequence[tuple[ProductSupplier, Supplier]]:
        return self.suppliers.get_product_suppliers(product_id)

    def get_preferred_supplier(self, product_id: int) -> tuple[ProductSupplier, Supplier] | None:
        return self.suppliers.get_preferred_supplier(product_id)
