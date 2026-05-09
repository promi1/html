"""Entry point: wires up aiogram dispatcher, FunPay client, DB, and AI helper."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .ai import AIClient
from .bot.handlers import all_routers
from .bot.middlewares import AdminOnlyMiddleware
from .config import Settings, get_settings
from .db import Database
from .funpay import FunPayClient


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


async def _amain(settings: Settings) -> None:
    settings.ensure_dirs()
    db = Database(settings.db_path)
    await db.init()

    funpay: FunPayClient | None = None
    if settings.funpay_golden_key is not None:
        funpay = FunPayClient(
            golden_key=settings.funpay_golden_key.get_secret_value(),
            user_agent=settings.funpay_user_agent,
            proxy=settings.funpay_proxy,
        )
        await funpay.__aenter__()
        try:
            await funpay.bootstrap()
        except Exception as exc:  # noqa: BLE001
            logging.warning("FunPay bootstrap failed: %s", exc)

    ai = AIClient(
        api_key=(
            settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        ),
        model=settings.openai_model,
    )

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.update.middleware(AdminOnlyMiddleware(settings.telegram_admin_ids))

    extra: dict[str, Any] = {
        "settings": settings,
        "db": db,
        "ai": ai,
        "funpay": funpay,
    }

    for router in all_routers():
        dispatcher.include_router(router)

    try:
        await dispatcher.start_polling(bot, **extra)
    finally:
        await bot.session.close()
        if funpay is not None:
            await funpay.__aexit__(None, None, None)


def run() -> None:
    """Console-script entry point (`funpay-tg-bot`)."""
    settings = get_settings()
    _configure_logging(settings.log_level)
    asyncio.run(_amain(settings))


if __name__ == "__main__":
    run()
