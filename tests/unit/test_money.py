"""Unit tests for money helpers (Decimal-safe currency arithmetic)."""

from __future__ import annotations

from decimal import Decimal

from domain.money import format_money, to_db, to_money


def test_to_money_quantizes_to_two_places():
    assert to_money("10.005") == Decimal("10.01")
    assert to_money(2.5) == Decimal("2.50")
    assert to_money(None) == Decimal("0.00")


def test_to_money_adds_without_float_drift():
    total = to_money("0.10") + to_money("0.20")
    assert total == Decimal("0.30")
    assert str(total) == "0.30"


def test_to_db_returns_float_or_none():
    assert to_db(Decimal("12.34")) == 12.34
    assert to_db(None) is None


def test_format_money_uses_symbol_and_grouping():
    assert format_money("1234.5") == "\u20b91,234.50"
