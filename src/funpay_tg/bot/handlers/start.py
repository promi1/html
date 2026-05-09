"""`/start` and main-menu handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...funpay import FunPayClient, FunPayError
from .. import keyboards

router = Router(name="start")
logger = logging.getLogger(__name__)


HELLO_TEXT = (
    "👋 <b>FunPay TG Bot</b>\n"
    "Личный бот для управления продавцом FunPay.\n\n"
    "Выбери раздел:"
)


@router.message(Command("start"))
async def on_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELLO_TEXT, reply_markup=keyboards.main_menu())


@router.callback_query(F.data == "menu:home")
async def on_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if call.message:
        try:
            await call.message.edit_text(HELLO_TEXT, reply_markup=keyboards.main_menu())
        except Exception:
            await call.message.answer(HELLO_TEXT, reply_markup=keyboards.main_menu())
    await call.answer()


@router.callback_query(F.data == "menu:status")
async def on_status(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await call.answer(
            "FUNPAY_GOLDEN_KEY не задан в .env — функционал FunPay недоступен.",
            show_alert=True,
        )
        return
    try:
        account = await funpay.bootstrap()
    except FunPayError as exc:
        await call.answer(f"Ошибка FunPay: {exc}", show_alert=True)
        return
    text = (
        "📊 <b>Статус аккаунта</b>\n"
        f"Пользователь: <code>{account.username}</code> (id={account.user_id})\n"
        f"Баланс: {account.balance} {account.currency}\n"
        f"Активные продажи: {account.active_sales}\n"
        f"Активные покупки: {account.active_purchases}\n"
        f"Локаль: {account.locale}\n"
        f"Игр загружено: {len(funpay.categories)}"
    )
    if call.message:
        await call.message.answer(text, reply_markup=keyboards.back_button())
    await call.answer()
