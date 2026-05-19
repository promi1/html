from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database import get_user, get_active_subscription
from config import config
from emoji import INFO, MONEY, STATS, SETTINGS, ARROW_UP, STOP, KEY, ROCKET

router = Router()


async def profile_text(user_id: int) -> str:
    user = await get_user(user_id)
    balance = user["balance"] if user else 0
    sub = await get_active_subscription(user_id)

    lines = [
        f"{INFO} <b>Мой профиль</b>\n",
        f"\U0001f464 ID: <code>{user_id}</code>",
        f"{MONEY} Баланс: <b>{balance:.0f} \u20bd</b>",
    ]

    if sub:
        expires = datetime.fromisoformat(sub["expires_at"])
        days_left = (expires - datetime.utcnow()).days
        lines.append(f"\n\U0001f7e2 <b>VPN:</b> Активен")
        lines.append(f"\u23f3 До: {expires.strftime('%d.%m.%Y')} ({days_left} дн.)")
    else:
        lines.append(f"\n\U0001f534 <b>VPN:</b> Неактивен")

    return "\n".join(lines)


def profile_kb(has_sub: bool) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"{ARROW_UP} Пополнить", callback_data="topup"),
        ],
    ]
    if has_sub:
        buttons.append([InlineKeyboardButton(text=f"{KEY} Мои ключи", callback_data="my_keys")])
    else:
        buttons.append([InlineKeyboardButton(text=f"{ROCKET} Купить VPN", callback_data="buy_vpn")])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f В меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    text = await profile_text(message.from_user.id)
    sub = await get_active_subscription(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=profile_kb(sub is not None))


@router.callback_query(F.data == "profile")
async def profile_callback(call: CallbackQuery):
    text = await profile_text(call.from_user.id)
    sub = await get_active_subscription(call.from_user.id)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=profile_kb(sub is not None))
