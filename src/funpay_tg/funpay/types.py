"""Lightweight dataclass models for FunPay entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SubCategoryType(StrEnum):
    """Type of FunPay subcategory."""

    COMMON = "lots"  # /lots/{id}/
    CURRENCY = "chips"  # /chips/{id}/ (currency / chips)


@dataclass(slots=True)
class SubCategory:
    """A subcategory within a game/category (e.g. 'Accounts', 'Top-up')."""

    id: int
    name: str
    type: SubCategoryType
    game_id: int


@dataclass(slots=True)
class Category:
    """A game / app on FunPay (e.g. 'Steam', 'Genshin Impact')."""

    id: int
    name: str
    subcategories: list[SubCategory] = field(default_factory=list)


@dataclass(slots=True)
class Account:
    """Bootstrap info about the authenticated FunPay account."""

    user_id: int
    username: str
    csrf_token: str
    balance: int
    currency: str
    active_sales: int
    active_purchases: int
    locale: str
    phpsessid: str | None


@dataclass(slots=True)
class ChatPreview:
    """Short preview of a chat (as shown in the chat list panel)."""

    id: int
    name: str
    last_message: str
    unread: bool


@dataclass(slots=True)
class Message:
    """A single message inside a chat."""

    id: int
    author_id: int
    author_name: str | None
    text: str | None
    image_url: str | None
    raw_html: str


@dataclass(slots=True)
class MyLot:
    """A seller's own lot in a subcategory."""

    id: str
    description: str | None
    server: str | None
    side: str | None
    amount: int | None
    price: float
    currency: str | None
    auto: bool
    active: bool


@dataclass(slots=True)
class LotFields:
    """Editable fields of a lot, parsed from the offerEdit form."""

    lot_id: int | None
    subcategory_id: int
    fields: dict[str, str]
