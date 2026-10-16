"""Unit tests for domain policies (validation, FEFO, status)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from domain.entities import InventoryBatch, Product
from domain.enums import StockStatus
from domain.exceptions import ValidationError
from domain.policies import StockPolicy, fefo_order, is_expired


def _batch(batch_id: int, qty: float, expiry: str | None, received: str = "2026-01-01") -> InventoryBatch:
    return InventoryBatch(
        id=batch_id, product_id=1, quantity_received=qty, quantity_remaining=qty,
        expiry_date=expiry, received_at=received,
    )


class TestValidation:
    def test_valid_product_passes(self):
        StockPolicy.validate_product_data(Product(sku="A", name="Apple"))

    def test_missing_sku_rejected(self):
        with pytest.raises(ValidationError):
            StockPolicy.validate_product_data(Product(sku="  ", name="Apple"))

    def test_missing_name_rejected(self):
        with pytest.raises(ValidationError):
            StockPolicy.validate_product_data(Product(sku="A", name=""))

    def test_negative_price_rejected(self):
        with pytest.raises(ValidationError):
            StockPolicy.validate_product_data(Product(sku="A", name="Apple", selling_price=-1))

    def test_non_positive_quantity_rejected(self):
        with pytest.raises(ValidationError):
            StockPolicy.validate_positive(0, "quantity")


class TestExpiryAndFefo:
    def test_is_expired_true_for_past_date(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        assert is_expired(_batch(1, 5, yesterday)) is True

    def test_is_expired_false_for_future_and_none(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        assert is_expired(_batch(1, 5, tomorrow)) is False
        assert is_expired(_batch(2, 5, None)) is False

    def test_fefo_excludes_expired_and_orders_by_expiry(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        soon = (date.today() + timedelta(days=2)).isoformat()
        later = (date.today() + timedelta(days=20)).isoformat()
        batches = [_batch(1, 10, yesterday), _batch(2, 8, later), _batch(3, 5, soon), _batch(4, 7, None)]
        ordered = fefo_order(batches)
        assert [b.id for b in ordered] == [3, 2, 4]  # soon, later, no-expiry last

    def test_fefo_skips_depleted(self):
        soon = (date.today() + timedelta(days=2)).isoformat()
        depleted = _batch(1, 0, soon)
        available = _batch(2, 4, soon)
        assert [b.id for b in fefo_order([depleted, available])] == [2]


class TestStatusDerivation:
    def test_out_of_stock(self):
        assert StockPolicy.derive_status(0, 10) == StockStatus.OUT_OF_STOCK

    def test_low(self):
        assert StockPolicy.derive_status(5, 10) == StockStatus.LOW

    def test_healthy(self):
        assert StockPolicy.derive_status(50, 10) == StockStatus.HEALTHY

    def test_expired_takes_precedence(self):
        assert StockPolicy.derive_status(20, 10, expired_present=True) == StockStatus.EXPIRED
