from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from database import get_user, get_active_subscription, get_traffic, ensure_traffic_table
from config import config
from emoji import CHECK, CROSS, MONEY, STATS, SETTINGS, ARROW_UP, STOP, KEY, ROCKET


def fmt_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b / (1024*1024):.1f} MB"
    else:
        return f"{b / (1024*1024*1024):.2f} GB"

router = Router()


async def profile_text(user_id: int) -> str:
    user = await get_user(user_id)
    balance = user["balance"] if user else 0
    sub = await get_active_subscription(user_id)

    lines = [
        f"<b>Мой профиль</b>\n",
        f"ID: <code>{user_id}</code>",
        f"Баланс: <b>{balance:.0f} \u20bd</b>",
    ]

    if sub:
        expires = datetime.fromisoformat(sub["expires_at"])
        days_left = (expires - datetime.utcnow()).days
        lines.append(f"\n<b>VPN:</b> Активен")
        lines.append(f"До: {expires.strftime('%d.%m.%Y')} ({days_left} дн.)")
        await ensure_traffic_table()
        traffic = await get_traffic(user_id)
        up = traffic.get("upload", 0)
        down = traffic.get("download", 0)
        total = up + down
        lines.append(f"\nТрафик: {fmt_bytes(total)}")
        lines.append(f"  Upload: {fmt_bytes(up)}")
        lines.append(f"  Download: {fmt_bytes(down)}")
    else:
        lines.append(f"\n<b>VPN:</b> Неактивен")

    return "\n".join(lines)


def profile_kb(has_sub: bool) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Пополнить", callback_data="topup"),
        ],
    ]
    if has_sub:
        buttons.append([InlineKeyboardButton(text="Мои ключи", callback_data="my_keys")])
    else:
        buttons.append([InlineKeyboardButton(text="Купить VPN", callback_data="buy_vpn")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="main_menu")])
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
