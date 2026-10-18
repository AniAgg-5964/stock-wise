"""StockWise — domain exceptions.

Services raise these; the UI converts them into friendly messages.
"""

from __future__ import annotations


class StockWiseError(Exception):
    """Base class for all StockWise domain errors."""


class ValidationError(StockWiseError):
    """A field failed business validation."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class NotFoundError(StockWiseError):
    """A requested entity does not exist."""

    def __init__(self, entity: str, identifier: object) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} not found: {identifier}")


class DuplicateImportError(StockWiseError):
    """A duplicate receipt/sale import was detected (idempotency guard)."""

    def __init__(self, reference: object = None) -> None:
        self.reference = reference
        super().__init__(f"Duplicate import detected for reference: {reference}")


class InsufficientStockError(StockWiseError):
    """A sale/consumption exceeds usable stock and no override was given."""

    def __init__(self, requested: float, available: float, message: str | None = None) -> None:
        self.requested = requested
        self.available = available
        super().__init__(
            message or f"Insufficient stock: requested {requested}, available {available}"
        )


class InvalidMovementError(StockWiseError):
    """A stock movement would violate ledger invariants."""


class ModelUnavailableError(StockWiseError):
    """No usable forecast model/fallback is available."""


class TinyFishError(StockWiseError):
    """TinyFish supplier research failed (never blocks core workflows)."""


class ResearchNotConfiguredError(TinyFishError):
    """Supplier research was requested but no API key is configured."""
