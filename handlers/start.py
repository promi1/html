from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command

from database import get_or_create_user, get_active_subscription
from config import config
from emoji import (BUTTERFLY, SETTINGS, PLUS, INFO, MESSAGE, WARNING,
                   SHIELD, KEY, ROCKET, GLOBE, LOCK)

router = Router()


async def check_channel_subscription(bot: Bot, user_id: int) -> bool:
    if not config.CHANNEL_ID:
        return True
    try:
        member = await bot.get_chat_member(config.CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return True


def main_menu_kb(has_sub: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"{ROCKET} Купить VPN", callback_data="buy_vpn"),
            InlineKeyboardButton(text=f"{PLUS} Пополнить", callback_data="topup"),
        ],
        [
            InlineKeyboardButton(text=f"{INFO} Мой профиль", callback_data="profile"),
            InlineKeyboardButton(text=f"{KEY} Мои ключи", callback_data="my_keys"),
        ],
        [
            InlineKeyboardButton(text=f"{GLOBE} Туториалы", callback_data="tutorials"),
            InlineKeyboardButton(text=f"{WARNING} Помощь", callback_data="help"),
        ],
    ]

    if config.RULES_URL:
        buttons.append([
            InlineKeyboardButton(text=f"{LOCK} Правила", url=config.RULES_URL)
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channel_sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\U0001f514 Подписаться на канал", url=config.CHANNEL_URL)],
        [InlineKeyboardButton(text="\u2705 Я подписался", callback_data="check_sub")]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    if not await check_channel_subscription(bot, message.from_user.id):
        await message.answer(
            f"{SHIELD} <b>Для использования бота подпишитесь на канал!</b>\n\n"
            f"После подписки нажмите кнопку ниже.",
            parse_mode="HTML",
            reply_markup=channel_sub_kb()
        )
        return

    name = message.from_user.first_name or "пользователь"
    sub = await get_active_subscription(message.from_user.id)
    has_sub = sub is not None

    await message.answer(
        f"{SHIELD} <b>Добро пожаловать, {name}!</b>\n\n"
        f"{ROCKET} Быстрый и надёжный VPN\n"
        f"{GLOBE} Серверы по всему миру\n"
        f"{LOCK} Протокол VLESS + XTLS-Reality\n\n"
        f"\U0001f4b0 <b>Стоимость:</b> {config.PRICE_RUB} \u20bd / месяц\n\n"
        f"Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(has_sub)
    )


@router.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, bot: Bot):
    if await check_channel_subscription(bot, call.from_user.id):
        await call.answer("\u2705 Подписка подтверждена!", show_alert=True)
        name = call.from_user.first_name or "пользователь"
        sub = await get_active_subscription(call.from_user.id)
        await call.message.edit_text(
            f"{SHIELD} <b>Добро пожаловать, {name}!</b>\n\n"
            f"{ROCKET} Быстрый и надёжный VPN\n"
            f"{GLOBE} Серверы по всему миру\n"
            f"{LOCK} Протокол VLESS + XTLS-Reality\n\n"
            f"\U0001f4b0 <b>Стоимость:</b> {config.PRICE_RUB} \u20bd / месяц\n\n"
            f"Выберите действие:",
            parse_mode="HTML",
            reply_markup=main_menu_kb(sub is not None)
        )
    else:
        await call.answer("\u274c Вы ещё не подписались на канал!", show_alert=True)


@router.callback_query(F.data == "main_menu")
async def back_to_menu(call: CallbackQuery):
    name = call.from_user.first_name or "пользователь"
    sub = await get_active_subscription(call.from_user.id)
    await call.message.edit_text(
        f"{SHIELD} <b>Главное меню</b>\n\n"
        f"Привет, {name}! Выберите действие:",
        parse_mode="HTML",
        reply_markup=main_menu_kb(sub is not None)
    )


@router.callback_query(F.data == "help")
async def help_handler(call: CallbackQuery):
    await call.message.edit_text(
        f"{WARNING} <b>Помощь / FAQ</b>\n\n"
        f"<b>Как подключиться?</b>\n"
        f"1. Купите подписку в боте\n"
        f"2. Скопируйте ссылку подписки\n"
        f"3. Вставьте в приложение (Happ / v2rayN / Hiddify)\n"
        f"4. Подключайтесь!\n\n"
        f"<b>Какие протоколы?</b>\n"
        f"VLESS + XTLS-Reality \u2014 самый быстрый и незаметный\n\n"
        f"<b>Не работает?</b>\n"
        f"\u2022 Проверьте что ссылка скопирована целиком\n"
        f"\u2022 Обновите подписку в приложении\n"
        f"\u2022 Попробуйте другой сервер\n\n"
        f"{MESSAGE} <b>Поддержка:</b> напишите администратору",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f Назад", callback_data="main_menu")]
        ])
    )
