"""Domain exceptions for the FunPay client."""

from __future__ import annotations


class FunPayError(Exception):
    """Base class for all FunPay client errors."""


class UnauthorizedError(FunPayError):
    """Raised when FunPay rejects the golden_key (login redirect / 403)."""


class RequestFailedError(FunPayError):
    """Raised when an HTTP request returns a non-success status."""

    def __init__(self, status: int, body: str | None = None):
        self.status = status
        self.body = body
        super().__init__(f"FunPay request failed with status {status}")


class MessageNotDeliveredError(FunPayError):
    """Raised when FunPay rejects sending a chat message (rate-limit, etc.)."""

    def __init__(self, chat_id: int | str, error: str | None):
        self.chat_id = chat_id
        self.error = error
        super().__init__(f"Message to chat {chat_id} not delivered: {error}")


class ImageUploadError(FunPayError):
    """Raised when image upload fails."""


class LotSavingError(FunPayError):
    """Raised when FunPay rejects saving a lot."""

    def __init__(self, error: str | None, field_errors: dict[str, str] | None = None):
        self.error = error
        self.field_errors = field_errors or {}
        super().__init__(f"Lot saving failed: {error}")


class CategoryNotFoundError(FunPayError):
    """Raised when a requested category id is not present on the home page."""
