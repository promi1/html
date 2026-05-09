"""Sell flow: search game → pick subcategory → fill description → save lot."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...ai import AIClient
from ...db import Database
from ...funpay import FunPayClient, FunPayError
from ...funpay.types import LotFields, SubCategoryType
from .. import keyboards
from ..states import SellStates

router = Router(name="sell")
logger = logging.getLogger(__name__)


_DRAFT_KEY = "sell_draft"


@router.callback_query(F.data == "menu:sell")
async def on_open(
    call: CallbackQuery, funpay: FunPayClient | None, state: FSMContext
) -> None:
    await state.clear()
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
        "🛒 <b>Создание лота</b>\n"
        "Выбери игру / приложение или нажми 🔍 чтобы ввести название."
    )
    keyboard = keyboards.categories_keyboard(funpay.categories, page=0)
    if call.message:
        try:
            await call.message.edit_text(text, reply_markup=keyboard)
        except Exception:
            await call.message.answer(text, reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data.startswith("sell:catpage:"))
async def on_categories_page(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await call.answer("FunPay не подключён.", show_alert=True)
        return
    page = int(call.data.rsplit(":", 1)[-1])
    keyboard = keyboards.categories_keyboard(funpay.categories, page=page)
    if call.message:
        await call.message.edit_reply_markup(reply_markup=keyboard)
    await call.answer()


@router.callback_query(F.data == "sell:search")
async def on_search(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SellStates.waiting_for_game_query)
    if call.message:
        await call.message.answer(
            "Введи название игры или приложения для поиска (как на FunPay)."
        )
    await call.answer()


@router.message(SellStates.waiting_for_game_query)
async def on_search_query(
    message: Message, state: FSMContext, funpay: FunPayClient | None
) -> None:
    if funpay is None:
        await message.answer("FunPay не подключён.")
        await state.clear()
        return
    query = (message.text or "").strip()
    if not query:
        await message.answer("Нужен текстовый запрос.")
        return
    matches = funpay.search_categories(query)
    if not matches:
        await message.answer("Ничего не нашлось. Попробуй другое название.")
        return
    await state.clear()
    await message.answer(
        f"Найдено: {len(matches)}. Выбери игру:",
        reply_markup=keyboards.categories_keyboard(matches, page=0),
    )


@router.callback_query(F.data == "sell:back")
async def on_back_to_games(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await call.answer("FunPay не подключён.", show_alert=True)
        return
    keyboard = keyboards.categories_keyboard(funpay.categories, page=0)
    if call.message:
        await call.message.edit_text(
            "🛒 <b>Создание лота</b>\nВыбери игру / приложение.", reply_markup=keyboard
        )
    await call.answer()


@router.callback_query(F.data.startswith("sell:cat:"))
async def on_pick_category(call: CallbackQuery, funpay: FunPayClient | None) -> None:
    if funpay is None:
        await call.answer("FunPay не подключён.", show_alert=True)
        return
    category_id = int(call.data.rsplit(":", 1)[-1])
    category = funpay.get_category(category_id)
    if category is None:
        await call.answer("Категория не найдена.", show_alert=True)
        return
    if not category.subcategories:
        await call.answer("Подкатегорий нет.", show_alert=True)
        return
    text = (
        f"🎮 <b>{category.name}</b>\n"
        "Выбери раздел (аккаунты, рефералы, прочее, подписки и т.д.):"
    )
    if call.message:
        await call.message.edit_text(text, reply_markup=keyboards.subcategories_keyboard(category))
    await call.answer()


@router.callback_query(F.data.startswith("sell:sub:"))
async def on_pick_subcategory(
    call: CallbackQuery, funpay: FunPayClient | None, state: FSMContext, db: Database
) -> None:
    if funpay is None:
        await call.answer("FunPay не подключён.", show_alert=True)
        return
    parts = call.data.split(":")
    sub_id = int(parts[2])
    sub_type = parts[3]
    if sub_type != SubCategoryType.COMMON.value:
        await call.answer(
            "Создание лота поддерживается только для обычных разделов (lots).",
            show_alert=True,
        )
        return

    draft = {"subcategory_id": sub_id, "photo_paths": []}
    await state.update_data(**{_DRAFT_KEY: draft})
    if call.from_user:
        await db.save_draft(call.from_user.id, draft)
    await state.set_state(SellStates.waiting_for_short_description)
    if call.message:
        await call.message.answer(
            "📝 Введи <b>краткое описание</b> (название лота, заголовок).\n"
            "Например: <i>Аккаунт Steam с играми</i>"
        )
    await call.answer()


@router.message(SellStates.waiting_for_short_description)
async def on_short_description(
    message: Message, state: FSMContext, db: Database
) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текст краткого описания.")
        return
    data = await state.get_data()
    draft = dict(data.get(_DRAFT_KEY) or {})
    draft["short_description"] = text
    await state.update_data(**{_DRAFT_KEY: draft})
    if message.from_user:
        await db.save_draft(message.from_user.id, draft)
    await state.set_state(SellStates.waiting_for_full_description)
    await message.answer(
        "📜 Теперь подробное описание лота. Можно несколько строк, ссылки и эмодзи.\n"
        "Когда напишешь — нажми ✅ или 🤖 для AI-улучшения.",
        reply_markup=keyboards.sell_description_keyboard(),
    )


@router.message(SellStates.waiting_for_full_description)
async def on_full_description(
    message: Message, state: FSMContext, db: Database
) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    data = await state.get_data()
    draft = dict(data.get(_DRAFT_KEY) or {})
    draft["full_description"] = text
    await state.update_data(**{_DRAFT_KEY: draft})
    if message.from_user:
        await db.save_draft(message.from_user.id, draft)
    await message.answer(
        "Описание сохранено. Что дальше?",
        reply_markup=keyboards.sell_description_keyboard(),
    )


@router.callback_query(F.data == "sell:ai")
async def on_ai_improve(call: CallbackQuery, ai: AIClient, state: FSMContext) -> None:
    if not ai.is_enabled:
        await call.answer("OpenAI ключ не задан в .env", show_alert=True)
        return
    data = await state.get_data()
    draft = data.get(_DRAFT_KEY) or {}
    raw = draft.get("full_description") or draft.get("short_description")
    if not raw:
        await call.answer("Сначала напиши черновик описания.", show_alert=True)
        return
    try:
        improved = await ai.improve_description(str(raw))
    except RuntimeError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    new_draft = dict(draft)
    new_draft["full_description"] = improved
    await state.update_data(**{_DRAFT_KEY: new_draft})
    if call.message:
        await call.message.answer(
            "🤖 <b>AI-описание:</b>\n" + improved,
            reply_markup=keyboards.sell_description_keyboard(),
        )
    await call.answer()


@router.callback_query(F.data == "sell:edit")
async def on_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SellStates.waiting_for_full_description)
    if call.message:
        await call.message.answer("Перепиши описание одним сообщением.")
    await call.answer()


@router.callback_query(F.data == "sell:next")
async def on_next(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    draft = data.get(_DRAFT_KEY) or {}
    if not draft.get("full_description"):
        await call.answer("Сначала введи описание.", show_alert=True)
        return
    await state.set_state(SellStates.waiting_for_price)
    if call.message:
        await call.message.answer(
            "💸 Цена лота в валюте аккаунта (только число, без знаков):"
        )
    await call.answer()


@router.message(SellStates.waiting_for_price)
async def on_price(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").replace(",", ".").strip()
    try:
        price = float(raw)
    except ValueError:
        await message.answer("Цена должна быть числом, например 250 или 199.99.")
        return
    if price <= 0:
        await message.answer("Цена должна быть положительной.")
        return
    data = await state.get_data()
    draft = dict(data.get(_DRAFT_KEY) or {})
    draft["price"] = price
    await state.update_data(**{_DRAFT_KEY: draft})
    if message.from_user:
        await db.save_draft(message.from_user.id, draft)
    await state.set_state(SellStates.waiting_for_amount)
    await message.answer("📦 Количество (целое число, например 1 или 50):")


@router.message(SellStates.waiting_for_amount)
async def on_amount(message: Message, state: FSMContext, db: Database) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Количество должно быть целым числом.")
        return
    amount = int(raw)
    if amount <= 0:
        await message.answer("Количество должно быть больше 0.")
        return
    data = await state.get_data()
    draft = dict(data.get(_DRAFT_KEY) or {})
    draft["amount"] = amount
    await state.update_data(**{_DRAFT_KEY: draft})
    if message.from_user:
        await db.save_draft(message.from_user.id, draft)
    await _show_summary(message, draft)


async def _show_summary(message: Message, draft: dict) -> None:
    text = (
        "📝 <b>Сводка лота</b>\n"
        f"Раздел (subcategory_id): <code>{draft.get('subcategory_id')}</code>\n"
        f"Заголовок: {draft.get('short_description', '—')}\n"
        f"Цена: {draft.get('price', '—')}\n"
        f"Количество: {draft.get('amount', '—')}\n"
        f"Фото: {len(draft.get('photo_paths') or [])} шт.\n\n"
        "<b>Описание:</b>\n"
        f"{draft.get('full_description', '—')}"
    )
    await message.answer(text, reply_markup=keyboards.sell_summary_keyboard())


@router.callback_query(F.data == "sell:photo")
async def on_photo_request(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SellStates.waiting_for_photo)
    if call.message:
        await call.message.answer("Пришли одно или несколько фото для лота.")
    await call.answer()


@router.message(SellStates.waiting_for_photo, F.photo)
async def on_photo(message: Message, state: FSMContext, db: Database) -> None:
    if not message.photo or not message.bot:
        return
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    if not file.file_path:
        await message.answer("Не удалось получить путь к файлу.")
        return
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await message.bot.download_file(file.file_path, destination=tmp.name)
        tmp_path = tmp.name
    data = await state.get_data()
    draft = dict(data.get(_DRAFT_KEY) or {})
    draft.setdefault("photo_paths", []).append(tmp_path)
    await state.update_data(**{_DRAFT_KEY: draft})
    if message.from_user:
        await db.save_draft(message.from_user.id, draft)
    await message.answer(
        f"📸 Сохранено фото ({len(draft['photo_paths'])} в очереди). "
        "Можешь прислать ещё или нажми /done."
    )


@router.message(SellStates.waiting_for_photo, F.text == "/done")
async def on_photo_done(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    draft = data.get(_DRAFT_KEY) or {}
    await _show_summary(message, draft)


@router.callback_query(F.data == "sell:cancel")
async def on_cancel(call: CallbackQuery, state: FSMContext, db: Database) -> None:
    await state.clear()
    if call.from_user:
        await db.delete_draft(call.from_user.id)
    if call.message:
        await call.message.answer("Создание лота отменено.", reply_markup=keyboards.main_menu())
    await call.answer()


@router.callback_query(F.data == "sell:submit")
async def on_submit(
    call: CallbackQuery,
    funpay: FunPayClient | None,
    state: FSMContext,
    db: Database,
) -> None:
    if funpay is None:
        await call.answer("FunPay не подключён.", show_alert=True)
        return
    data = await state.get_data()
    draft = data.get(_DRAFT_KEY) or {}
    sub_id = draft.get("subcategory_id")
    if not sub_id:
        await call.answer("Нет подкатегории.", show_alert=True)
        return
    try:
        form = await funpay.get_lot_form(subcategory_id=int(sub_id))
        _apply_draft(form, draft)
        await funpay.save_lot(form)
    except FunPayError as exc:
        await call.answer(f"Ошибка: {exc}", show_alert=True)
        if call.message:
            await call.message.answer(f"❌ <b>Не удалось создать лот.</b>\n{exc}")
        return
    await state.clear()
    if call.from_user:
        await db.delete_draft(call.from_user.id)
    if call.message:
        await call.message.answer(
            "✅ Лот создан/обновлён.",
            reply_markup=keyboards.main_menu(),
        )
    await call.answer()


def _apply_draft(form: LotFields, draft: dict) -> None:
    """Map draft values onto the parsed offerEdit form fields."""
    fields = form.fields
    fields["fields[summary][ru]"] = draft.get("short_description", "")
    fields["fields[summary][en]"] = draft.get("short_description", "")
    fields["fields[desc][ru]"] = draft.get("full_description", "")
    fields["fields[desc][en]"] = draft.get("full_description", "")
    if draft.get("price") is not None:
        fields["price"] = f"{draft['price']:.2f}"
    if draft.get("amount") is not None:
        fields["amount"] = str(draft["amount"])
    fields["active"] = "on"
    fields.setdefault("deleted", "")
    _ = Path  # suppress unused import warning if any
