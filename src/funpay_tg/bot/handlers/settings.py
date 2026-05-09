"""Settings overview (read-only — actual values come from .env)."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ...config import Settings
from .. import keyboards

router = Router(name="settings")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:settings")
async def on_open(call: CallbackQuery, settings: Settings) -> None:
    text = _format_settings(settings)
    if call.message:
        try:
            await call.message.edit_text(text, reply_markup=keyboards.back_button())
        except Exception:
            await call.message.answer(text, reply_markup=keyboards.back_button())
    await call.answer()


def _format_settings(settings: Settings) -> str:
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"FUNPAY_GOLDEN_KEY: {_mask(settings.funpay_golden_key.get_secret_value() if settings.funpay_golden_key else None)}\n"
        f"FUNPAY_PROXY: {settings.funpay_proxy or '—'}\n"
        f"OPENAI_API_KEY: {_mask(settings.openai_api_key.get_secret_value() if settings.openai_api_key else None)}\n"
        f"OPENAI_MODEL: {settings.openai_model}\n"
        f"DB_PATH: <code>{settings.db_path}</code>\n"
        f"MEDIA_DIR: <code>{settings.media_dir}</code>\n"
        f"LOG_LEVEL: {settings.log_level}\n\n"
        "<i>Изменяй значения в файле .env и перезапускай бот.</i>"
    )


def _mask(value: str | None) -> str:
    if not value:
        return "—"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"
