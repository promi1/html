import uuid
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import get_user, create_payment
from services.cryptopay import create_crypto_invoice
from services.lolz import create_lolz_invoice
from config import config
from emoji import (PLUS, ARROW_UP, USDT, DOLPHIN, FIRE, GOLD, LOLZ,
                   MONEY, INFO, CHECK, CROSS, STOP)

router = Router()

AMOUNTS = [119, 200, 500, 1000]

CRYPTO_CURRENCIES = [
    ("USDT", USDT, "USDT"),
    ("TON",  DOLPHIN, "TON"),
    ("TRX",  FIRE, "TRX (TRON)"),
    ("BTC",  GOLD, "BTC"),
]


def topup_menu_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="CryptoBot", callback_data="pay_crypto")],
    ]
    if config.LOLZ_TOKEN:
        buttons.append([InlineKeyboardButton(text="Lolz.live", callback_data="pay_lolz")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def amount_kb(method: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for amt in AMOUNTS:
        row.append(InlineKeyboardButton(
            text=f"{amt} \u20bd", callback_data=f"amount:{method}:{amt}"
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Назад", callback_data="topup")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def crypto_currency_kb(amount: int) -> InlineKeyboardMarkup:
    rows = []
    for code, emoji_val, label in CRYPTO_CURRENCIES:
        rows.append([InlineKeyboardButton(
            text=f"{label}", callback_data=f"crypto_pay:{code}:{amount}"
        )])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="pay_crypto")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "topup")
async def topup_menu(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    balance = user["balance"] if user else 0

    methods_text = "<b>CryptoBot</b> \u2014 USDT, TON, TRX, BTC"
    if config.LOLZ_TOKEN:
        methods_text += f"\n<b>Lolz.live</b> \u2014 рубли через маркетплейс"

    await call.message.edit_text(
        f"<b>Пополнение баланса</b>\n\n"
        f"Текущий баланс: <b>{balance:.0f} \u20bd</b>\n\n"
        f"Способы оплаты:\n{methods_text}\n\n"
        f"Выберите способ:",
        parse_mode="HTML",
        reply_markup=topup_menu_kb()
    )


@router.callback_query(F.data == "pay_crypto")
async def pay_crypto(call: CallbackQuery):
    if not config.CRYPTOPAY_TOKEN:
        await call.answer("\u26a0\ufe0f CryptoBot ещё не настроен", show_alert=True)
        return
    await call.message.edit_text(
        f"<b>Оплата через CryptoBot</b>\n\n"
        f"Выберите сумму пополнения:",
        parse_mode="HTML",
        reply_markup=amount_kb("crypto")
    )


@router.callback_query(F.data == "pay_lolz")
async def pay_lolz(call: CallbackQuery):
    if not config.LOLZ_TOKEN:
        await call.answer("\u26a0\ufe0f Lolz.live ещё не настроен", show_alert=True)
        return
    await call.message.edit_text(
        f"<b>Оплата через Lolz.live</b>\n\n"
        f"Оплата в рублях через аккаунт Lolz Market.\n"
        f"Выберите сумму:",
        parse_mode="HTML",
        reply_markup=amount_kb("lolz")
    )


@router.callback_query(F.data.startswith("amount:"))
async def amount_selected(call: CallbackQuery):
    _, method, amount_str = call.data.split(":")
    amount = int(amount_str)

    if method == "crypto":
        await call.message.edit_text(
                f"<b>Сумма: {amount} \u20bd</b>\n\n"
                f"Выберите криптовалюту:",
            parse_mode="HTML",
            reply_markup=crypto_currency_kb(amount)
        )
    elif method == "lolz":
        await _create_lolz_payment(call, amount)


async def _create_lolz_payment(call: CallbackQuery, amount: int):
    await call.message.edit_text(
        f"<b>Создаём счёт...</b>",
        parse_mode="HTML"
    )

    payment_id = f"lolz_{call.from_user.id}_{uuid.uuid4().hex[:8]}"
    callback_url = f"{config.WEBHOOK_BASE_URL}/webhook/lolz"
    bot_info = await call.bot.get_me()
    success_url = f"https://t.me/{bot_info.username}"

    invoice = await create_lolz_invoice(
        user_id=call.from_user.id,
        rub_amount=amount,
        payment_id=payment_id,
        callback_url=callback_url,
        success_url=success_url
    )

    if not invoice:
        await call.message.edit_text(
            f"<b>Ошибка создания счёта</b>\n\nПопробуйте позже.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад", callback_data="topup")]
            ])
        )
        return

    await create_payment(
        user_id=call.from_user.id,
        amount=amount,
        currency="RUB",
        method="lolz",
        payment_id=payment_id
    )

    await call.message.edit_text(
        f"<b>Счёт создан!</b>\n\n"
        f"Сумма: <b>{amount} \u20bd</b>\n"
        f"Действителен 1 час.\n\n"
        f"После оплаты баланс пополнится автоматически.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить на Lolz", url=invoice["url"])],
            [InlineKeyboardButton(text="Назад", callback_data="topup")]
        ])
    )


@router.callback_query(F.data.startswith("crypto_pay:"))
async def crypto_pay(call: CallbackQuery):
    _, currency, amount_str = call.data.split(":")
    amount = int(amount_str)

    await call.message.edit_text(
        f"<b>Создаём счёт в CryptoBot...</b>",
        parse_mode="HTML"
    )

    payment_id = f"cp_{call.from_user.id}_{uuid.uuid4().hex[:8]}"

    invoice = await create_crypto_invoice(
        user_id=call.from_user.id,
        rub_amount=amount,
        currency=currency,
        payment_id=payment_id,
        description=f"VPN {amount} \u20bd"
    )

    if not invoice:
        await call.message.edit_text(
            f"<b>Ошибка создания счёта</b>\n\nПопробуйте позже.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Назад", callback_data="pay_crypto")]
            ])
        )
        return

    await create_payment(
        user_id=call.from_user.id,
        amount=amount,
        currency=currency,
        method="cryptopay",
        payment_id=payment_id
    )

    emoji_map = {"USDT": USDT, "TON": DOLPHIN, "TRX": FIRE, "BTC": GOLD}
    cur_emoji = emoji_map.get(currency, "\U0001f48e")

    await call.message.edit_text(
        f"<b>Счёт создан!</b>\n\n"
        f"Сумма: <b>{amount} \u20bd</b>\n"
        f"Валюта: <b>{currency}</b>\n"
        f"Действителен 1 час.\n\n"
        f"После оплаты баланс пополнится автоматически.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить в CryptoBot", url=invoice.bot_invoice_url)],
            [InlineKeyboardButton(text="Назад", callback_data="topup")]
        ])
    )
