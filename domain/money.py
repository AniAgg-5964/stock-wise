"""StockWise — money helpers.

Money is handled as ``Decimal`` in the domain and converted to/from REAL only at
the SQLite boundary, avoiding binary floating-point drift in currency totals.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

_CENT = Decimal("0.01")


def to_money(value: Any) -> Decimal:
    """Coerce any numeric value to a 2-decimal ``Decimal``."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def to_db(value: Optional[Any]) -> Optional[float]:
    """Convert a monetary value for storage in SQLite (REAL)."""
    if value is None:
        return None
    return float(to_money(value))


def format_money(value: Any, symbol: str = "\u20b9") -> str:
    """Format a monetary value for display, e.g. ``₹1,234.50``."""
    return f"{symbol}{to_money(value):,.2f}"
