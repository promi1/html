"""Inline / reply keyboard factories for the Telegram bot."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..funpay.types import Category, SubCategory, SubCategoryType


def main_menu() -> InlineKeyboardMarkup:
    """Top-level menu shown by ``/start``."""
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Чаты", callback_data="menu:chats")
    builder.button(text="🛒 Продать", callback_data="menu:sell")
    builder.button(text="📦 Мои лоты", callback_data="menu:lots")
    builder.button(text="🌐 Прокси", callback_data="menu:proxies")
    builder.button(text="⚙️ Настройки", callback_data="menu:settings")
    builder.button(text="ℹ️ Статус", callback_data="menu:status")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def back_button(target: str = "menu:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data=target)]]
    )


def categories_keyboard(categories: list[Category], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    """Paginated list of games / categories. Used during the sell flow."""
    builder = InlineKeyboardBuilder()
    start = page * page_size
    chunk = categories[start : start + page_size]
    for cat in chunk:
        builder.button(text=cat.name, callback_data=f"sell:cat:{cat.id}")
    builder.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="◀️", callback_data=f"sell:catpage:{page - 1}")
    nav.button(text="🔍 Поиск", callback_data="sell:search")
    if start + page_size < len(categories):
        nav.button(text="▶️", callback_data=f"sell:catpage:{page + 1}")
    nav.adjust(3)
    builder.attach(nav)

    home = InlineKeyboardBuilder()
    home.button(text="◀️ В меню", callback_data="menu:home")
    builder.attach(home)
    return builder.as_markup()


def subcategories_keyboard(category: Category) -> InlineKeyboardMarkup:
    """Keyboard with subcategories of a category, COMMON-type first."""
    builder = InlineKeyboardBuilder()
    common = [s for s in category.subcategories if s.type == SubCategoryType.COMMON]
    others = [s for s in category.subcategories if s.type != SubCategoryType.COMMON]
    for sub in common + others:
        prefix = "💼" if sub.type == SubCategoryType.COMMON else "💎"
        builder.button(
            text=f"{prefix} {sub.name}", callback_data=f"sell:sub:{sub.id}:{sub.type.value}"
        )
    builder.adjust(1)

    nav = InlineKeyboardBuilder()
    nav.button(text="◀️ К играм", callback_data="sell:back")
    builder.attach(nav)
    return builder.as_markup()


def chats_keyboard(previews: list, page: int = 0, page_size: int = 8) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * page_size
    chunk = previews[start : start + page_size]
    for chat in chunk:
        marker = "🟡 " if chat.unread else ""
        text = f"{marker}{chat.name}"
        builder.button(text=text, callback_data=f"chats:open:{chat.id}")
    builder.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 0:
        nav.button(text="◀️", callback_data=f"chats:page:{page - 1}")
    nav.button(text="🔄", callback_data="chats:refresh")
    if start + page_size < len(previews):
        nav.button(text="▶️", callback_data=f"chats:page:{page + 1}")
    nav.adjust(3)
    builder.attach(nav)

    home = InlineKeyboardBuilder()
    home.button(text="◀️ В меню", callback_data="menu:home")
    builder.attach(home)
    return builder.as_markup()


def chat_actions_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Ответить", callback_data=f"chats:reply:{chat_id}")
    builder.button(text="🖼 Отправить фото", callback_data=f"chats:photo:{chat_id}")
    builder.button(text="🤖 AI-ответ", callback_data=f"chats:ai:{chat_id}")
    builder.button(text="🔄 Обновить", callback_data=f"chats:open:{chat_id}")
    builder.adjust(2, 2)

    home = InlineKeyboardBuilder()
    home.button(text="◀️ К чатам", callback_data="menu:chats")
    builder.attach(home)
    return builder.as_markup()


def sell_description_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 Улучшить через AI", callback_data="sell:ai")
    builder.button(text="✅ Принять", callback_data="sell:next")
    builder.button(text="✏️ Переписать", callback_data="sell:edit")
    builder.adjust(1)
    return builder.as_markup()


def sell_summary_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Создать лот", callback_data="sell:submit")
    builder.button(text="🖼 Добавить фото", callback_data="sell:photo")
    builder.button(text="❌ Отменить", callback_data="sell:cancel")
    builder.adjust(1)
    return builder.as_markup()


def proxies_keyboard(proxies: list, *, allow_clear: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in proxies:
        marker = "🟢" if p.is_active else "⚪"
        label = p.label or _short_proxy(p.url)
        builder.button(text=f"{marker} {label}", callback_data=f"prox:tog:{p.id}")
        builder.button(text="🗑", callback_data=f"prox:del:{p.id}")
    builder.adjust(2)

    actions = InlineKeyboardBuilder()
    actions.button(text="➕ Добавить", callback_data="prox:add")
    if allow_clear and proxies:
        actions.button(text="❌ Очистить все", callback_data="prox:clear")
    actions.button(text="◀️ В меню", callback_data="menu:home")
    actions.adjust(1)
    builder.attach(actions)
    return builder.as_markup()


def lots_keyboard(lots: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lot in lots:
        marker = "✅" if lot.active else "⛔"
        text = f"{marker} {(lot.description or 'Без описания')[:35]} — {lot.price:.0f}{lot.currency or ''}"
        builder.button(text=text, callback_data=f"lots:open:{lot.id}")
    builder.adjust(1)

    home = InlineKeyboardBuilder()
    home.button(text="◀️ В меню", callback_data="menu:home")
    builder.attach(home)
    return builder.as_markup()


def _short_proxy(url: str) -> str:
    """Return ``host:port`` from a proxy URL (hide credentials)."""
    if "@" in url:
        url = url.split("@", 1)[-1]
    if "://" in url:
        url = url.split("://", 1)[-1]
    return url


def subcategory_brief(sub: SubCategory) -> str:
    label = "услуги/прочее" if sub.type == SubCategoryType.CURRENCY else "лоты"
    return f"{sub.name} ({label})"
