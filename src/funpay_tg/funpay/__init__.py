"""Asynchronous FunPay client (auth via golden_key cookie)."""

from .client import FunPayClient
from .exceptions import (
    FunPayError,
    LotSavingError,
    MessageNotDeliveredError,
    UnauthorizedError,
)
from .types import Category, ChatPreview, LotFields, Message, MyLot, SubCategory

__all__ = [
    "FunPayClient",
    "FunPayError",
    "UnauthorizedError",
    "LotSavingError",
    "MessageNotDeliveredError",
    "Category",
    "SubCategory",
    "ChatPreview",
    "Message",
    "MyLot",
    "LotFields",
]
