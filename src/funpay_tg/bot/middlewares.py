"""ACL middleware: only listed admin user IDs may interact with the bot."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class AdminOnlyMiddleware(BaseMiddleware):
    """Block updates that don't originate from an allowed user."""

    def __init__(self, admin_ids: list[int]):
        self._admin_ids = set(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event)
        if user_id is None:
            return await handler(event, data)
        if user_id not in self._admin_ids:
            logger.warning("Rejected update from non-admin user %s", user_id)
            if isinstance(event, Message):
                await event.answer("Доступ запрещён.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ запрещён.", show_alert=True)
            return None
        return await handler(event, data)


def _extract_user_id(event: TelegramObject) -> int | None:
    user = getattr(event, "from_user", None)
    if user is not None:
        return user.id
    message = getattr(event, "message", None)
    if message is not None:
        msg_user = getattr(message, "from_user", None)
        if msg_user is not None:
            return msg_user.id
    return None
