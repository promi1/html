"""Chats: list, view history, send replies (text / photo / AI)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from ...ai import AIClient
from ...funpay import FunPayClient, FunPayError
from .. import keyboards
from ..states import ChatStates

router = Router(name="chats")
logger = logging.getLogger(__name__)

_PAGE_SIZE = 8


@router.callback_query(F.data == "menu:chats")
async def on_open(call: CallbackQuery, funpay: FunPayClient | None, state: FSMContext) -> None:
    await state.clear()
    await _render_list(call, funpay, page=0)


@router.callback_query(F.data.startswith("chats:page:"))
async def on_page(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    page = int(call.data.rsplit(":", 1)[-1])
    await _render_list(call, funpay, page=page)


@router.callback_query(F.data == "chats:refresh")
async def on_refresh(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    await _render_list(call, funpay, page=0)


async def _render_list(call: CallbackQuery, funpay: FunPayClient | None, *, page: int) -> None:
    if funpay is None:
        await call.answer("Сначала задай FUNPAY_GOLDEN_KEY в .env", show_alert=True)
        return
    try:
        if funpay.account is None:  # type: ignore[truthy-bool]
            await funpay.bootstrap()
    except Exception:
        await funpay.bootstrap()
    try:
        previews = await funpay.get_chat_previews()
    except FunPayError as exc:
        await call.answer(f"Ошибка FunPay: {exc}", show_alert=True)
        return

    if not previews:
        text = "💬 <b>Чаты</b>\nАктивных диалогов нет."
    else:
        unread = sum(1 for p in previews if p.unread)
        text = (
            "💬 <b>Чаты</b>\n"
            f"Всего: {len(previews)}, непрочитанных: {unread}.\n"
            "Открой диалог, чтобы посмотреть последние сообщения и ответить."
        )
    keyboard = keyboards.chats_keyboard(previews, page=page, page_size=_PAGE_SIZE)
    if call.message:
        try:
            await call.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await call.message.answer(text, reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data.startswith("chats:open:"))
async def on_open_chat(
    call: CallbackQuery, funpay: FunPayClient | None, state: FSMContext
) -> None:
    if funpay is None:
        await call.answer("FunPay не подключён.", show_alert=True)
        return
    chat_id = int(call.data.rsplit(":", 1)[-1])
    await state.update_data(chat_id=chat_id)
    try:
        history = await funpay.get_chat_history(chat_id)
    except FunPayError as exc:
        await call.answer(f"Ошибка FunPay: {exc}", show_alert=True)
        return
    text = _format_history(chat_id, history)
    keyboard = keyboards.chat_actions_keyboard(chat_id)
    if call.message:
        try:
            await call.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await call.message.answer(text, reply_markup=keyboard)
    await call.answer()


def _format_history(chat_id: int, history: list) -> str:
    lines = [f"💬 <b>Чат {chat_id}</b>", ""]
    for msg in history[-15:]:
        author = msg.author_name or f"#{msg.author_id}"
        body = msg.text or ("[фото]" if msg.image_url else "")
        if body and len(body) > 220:
            body = body[:217] + "…"
        lines.append(f"<b>{author}:</b> {body}")
    if len(history) > 15:
        lines.insert(2, f"<i>(показаны последние 15 из {len(history)})</i>")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("chats:reply:"))
async def on_reply(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(call.data.rsplit(":", 1)[-1])
    await state.set_state(ChatStates.waiting_for_text)
    await state.update_data(chat_id=chat_id)
    if call.message:
        await call.message.answer("Пришли текст ответа одним сообщением.")
    await call.answer()


@router.message(ChatStates.waiting_for_text)
async def on_reply_text(message: Message, state: FSMContext, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await message.answer("FunPay не подключён.")
        await state.clear()
        return
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not message.text or chat_id is None:
        await message.answer("Нужен текст.")
        return
    try:
        await funpay.send_message(int(chat_id), message.text)
    except FunPayError as exc:
        await message.answer(f"❌ Не отправлено: {exc}")
        return
    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено.",
        reply_markup=keyboards.chat_actions_keyboard(int(chat_id)),
    )


@router.callback_query(F.data.startswith("chats:photo:"))
async def on_photo_request(call: CallbackQuery, state: FSMContext) -> None:
    chat_id = int(call.data.rsplit(":", 1)[-1])
    await state.set_state(ChatStates.waiting_for_photo)
    await state.update_data(chat_id=chat_id)
    if call.message:
        await call.message.answer("Пришли фото или картинку.")
    await call.answer()


@router.message(ChatStates.waiting_for_photo, F.photo)
async def on_photo(message: Message, state: FSMContext, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await message.answer("FunPay не подключён.")
        await state.clear()
        return
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not message.photo or chat_id is None:
        await message.answer("Нужно фото.")
        return
    photo = message.photo[-1]
    bot = message.bot
    if bot is None:
        await message.answer("Не удалось получить файл (нет бот-контекста).")
        return
    file = await bot.get_file(photo.file_id)
    if not file.file_path:
        await message.answer("Не удалось получить путь к файлу.")
        return
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await bot.download_file(file.file_path, destination=tmp.name)
        tmp_path = Path(tmp.name)
    try:
        await funpay.send_image(int(chat_id), tmp_path)
    except FunPayError as exc:
        await message.answer(f"❌ Не отправлено: {exc}")
        return
    finally:
        try:
            await asyncio.to_thread(tmp_path.unlink)
        except OSError:
            pass
    await state.clear()
    await message.answer(
        "✅ Фото отправлено.",
        reply_markup=keyboards.chat_actions_keyboard(int(chat_id)),
    )


@router.callback_query(F.data.startswith("chats:ai:"))
async def on_ai(
    call: CallbackQuery, funpay: FunPayClient | None, ai: AIClient
) -> None:
    chat_id = int(call.data.rsplit(":", 1)[-1])
    if funpay is None or not ai.is_enabled:
        await call.answer("AI или FunPay не сконфигурированы.", show_alert=True)
        return
    try:
        history = await funpay.get_chat_history(chat_id)
    except FunPayError as exc:
        await call.answer(f"Ошибка FunPay: {exc}", show_alert=True)
        return
    snippet = "\n".join(
        f"{m.author_name or '?'}: {m.text or '[фото]'}" for m in history[-12:] if m.text or m.image_url
    )
    if not snippet:
        await call.answer("Нет сообщений для контекста.", show_alert=True)
        return
    try:
        suggestion = await ai.suggest_reply(snippet)
    except RuntimeError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    if call.message:
        await call.message.answer(
            "<b>AI-черновик:</b>\n" + suggestion,
            reply_markup=keyboards.chat_actions_keyboard(chat_id),
        )
    await call.answer()


# unused-but-imported helper to silence linters about FSInputFile
__all__ = ["router", "FSInputFile"]
