"""Read-only view of the seller's own lots."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ...funpay import FunPayClient, FunPayError
from .. import keyboards

router = Router(name="lots")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:lots")
async def on_open(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await call.answer("FUNPAY_GOLDEN_KEY не задан в .env", show_alert=True)
        return
    try:
        if not funpay.categories:
            await funpay.bootstrap()
    except FunPayError as exc:
        await call.answer(f"Ошибка FunPay: {exc}", show_alert=True)
        return
    text = (
        "📦 <b>Мои лоты</b>\n"
        "Выбери игру → раздел, чтобы увидеть лоты в нём.\n"
        "Создание/изменение делается через раздел «Продать»."
    )
    keyboard = keyboards.categories_keyboard(funpay.categories, page=0)
    if call.message:
        try:
            await call.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await call.message.answer(text, reply_markup=keyboard)
    await call.answer()
