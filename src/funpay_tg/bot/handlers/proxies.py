"""Proxy management handlers."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...db import Database
from ...funpay.proxies import normalise_proxy
from .. import keyboards
from ..states import ProxyStates

router = Router(name="proxies")
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "menu:proxies")
async def on_open(call: CallbackQuery, db: Database) -> None:
    await _render_list(call, db)


async def _render_list(call: CallbackQuery, db: Database) -> None:
    proxies = await db.list_proxies()
    text = (
        "🌐 <b>Прокси</b>\n"
        f"Всего: {len(proxies)} (активных: {sum(1 for p in proxies if p.is_active)})\n\n"
        "Поддерживаются HTTP, HTTPS и SOCKS5 (резидентские/ДЦ).\n"
        "Тык по строке — включить/выключить, 🗑 — удалить."
    )
    if call.message:
        try:
            await call.message.edit_text(text, reply_markup=keyboards.proxies_keyboard(proxies))
        except Exception:
            await call.message.answer(text, reply_markup=keyboards.proxies_keyboard(proxies))
    await call.answer()


@router.callback_query(F.data == "prox:add")
async def on_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProxyStates.waiting_for_url)
    if call.message:
        await call.message.answer(
            "Пришли строку прокси в одном из форматов:\n"
            "• <code>host:port</code>\n"
            "• <code>http://user:pass@host:port</code>\n"
            "• <code>socks5://user:pass@host:port</code>"
        )
    await call.answer()


@router.message(ProxyStates.waiting_for_url)
async def on_url(message: Message, state: FSMContext, db: Database) -> None:
    if not message.text:
        await message.answer("Нужен текст с URL прокси.")
        return
    try:
        url = normalise_proxy(message.text)
    except ValueError as exc:
        await message.answer(f"❌ Не похоже на прокси: {exc}")
        return
    await db.add_proxy(url)
    await state.clear()
    proxies = await db.list_proxies()
    await message.answer(
        f"✅ Прокси добавлен. Всего: {len(proxies)}.",
        reply_markup=keyboards.proxies_keyboard(proxies),
    )


@router.callback_query(F.data.startswith("prox:tog:"))
async def on_toggle(call: CallbackQuery, db: Database) -> None:
    proxy_id = int(call.data.rsplit(":", 1)[-1])
    proxies = {p.id: p for p in await db.list_proxies()}
    target = proxies.get(proxy_id)
    if target is None:
        await call.answer("Не найдено.", show_alert=True)
        return
    await db.toggle_proxy(proxy_id, not target.is_active)
    await _render_list(call, db)


@router.callback_query(F.data.startswith("prox:del:"))
async def on_delete(call: CallbackQuery, db: Database) -> None:
    proxy_id = int(call.data.rsplit(":", 1)[-1])
    await db.delete_proxy(proxy_id)
    await _render_list(call, db)


@router.callback_query(F.data == "prox:clear")
async def on_clear(call: CallbackQuery, db: Database) -> None:
    for p in await db.list_proxies():
        await db.delete_proxy(p.id)
    await _render_list(call, db)
