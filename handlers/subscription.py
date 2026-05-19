import uuid
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

from database import (get_user, deduct_balance, create_subscription,
                       get_active_subscription, get_active_vpn_servers,
                       get_relay_servers, renew_subscription,
                       get_traffic, ensure_traffic_table)
from config import config
from emoji import (BUTTERFLY, CHECK, CROSS, MONEY, ROCKET, ARROW_UP,
                   WARNING, BELL, STOP, INFO, STATS, KEY, GLOBE, SHIELD,
                   flag, FLAGS)

router = Router()


@router.callback_query(F.data == "buy_vpn")
async def buy_vpn(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    balance = user["balance"] if user else 0
    price = config.PRICE_RUB

    servers = await get_active_vpn_servers()
    relays = await get_relay_servers()

    server_lines = []
    for s in servers:
        cc = s["country_code"]
        f = flag(cc)
        name = s["display_name"] or s["country_name"] or cc
        server_lines.append(f"  {f} <b>{name}</b> \u00b7 {s['speed']}")

    if relays:
        for r in relays:
            cc = r["country_code"]
            f = flag(cc)
            name = r["display_name"] or "WHITELIST Relay"
            server_lines.append(f"  {f} <b>{name}</b> \u00b7 Relay")

    servers_text = "\n".join(server_lines) if server_lines else "  \u26a0\ufe0f Серверы не добавлены"

    sub = await get_active_subscription(call.from_user.id)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Купить за {price} \u20bd с баланса",
            callback_data="confirm_buy"
        )],
        [InlineKeyboardButton(text="Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
    ])

    status = ""
    if sub:
        expires = datetime.fromisoformat(sub["expires_at"])
        days_left = (expires - datetime.utcnow()).days
        status = (
            f"\n\U0001f7e2 <b>У вас есть активная подписка</b>\n"
            f"  До: {expires.strftime('%d.%m.%Y')} ({days_left} дн.)\n"
        )

    await call.message.edit_text(
        f"<b>Купить VPN-подписку</b>\n\n"
        f"Цена: <b>{price} \u20bd / месяц</b>\n"
        f"Ваш баланс: <b>{balance:.0f} \u20bd</b>\n"
        f"{status}\n"
        f"<b>Доступные серверы:</b>\n"
        f"{servers_text}\n\n"
        f"Все серверы включены в подписку.",
        parse_mode="HTML",
        reply_markup=kb
    )


@router.callback_query(F.data == "confirm_buy")
async def confirm_buy(call: CallbackQuery):
    user_id = call.from_user.id
    price = config.PRICE_RUB

    # Check existing sub
    existing = await get_active_subscription(user_id)
    if existing:
        # Extend existing subscription
        expires = datetime.fromisoformat(existing["expires_at"])
        if expires < datetime.utcnow():
            new_expires = datetime.utcnow() + timedelta(days=30)
        else:
            new_expires = expires + timedelta(days=30)

        success = await deduct_balance(user_id, price)
        if not success:
            await call.message.edit_text(
                f"<b>Недостаточно средств!</b>\n\n"
                f"Пополните баланс и попробуйте снова.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Пополнить", callback_data="topup")],
                    [InlineKeyboardButton(text="Назад", callback_data="buy_vpn")]
                ])
            )
            return

        await renew_subscription(existing["id"], new_expires.isoformat())

        await call.message.edit_text(
            f"<b>Подписка продлена!</b>\n\n"
            f"Действует до: <b>{new_expires.strftime('%d.%m.%Y')}</b>\n\n"
            f"Ваша ссылка подписки не изменилась.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Мои ключи", callback_data="my_keys")],
                [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
            ])
        )
        return

    # New subscription
    success = await deduct_balance(user_id, price)
    if not success:
        await call.message.edit_text(
            f"<b>Недостаточно средств!</b>\n\n"
            f"Пополните баланс и попробуйте снова.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Пополнить", callback_data="topup")],
                [InlineKeyboardButton(text="Назад", callback_data="buy_vpn")]
            ])
        )
        return

    now = datetime.utcnow()
    expires = now + timedelta(days=30)
    sub_token = uuid.uuid4().hex

    await create_subscription(
        user_id=user_id,
        started_at=now.isoformat(),
        expires_at=expires.isoformat(),
        sub_token=sub_token
    )

    # Build subscription URL
    from services.subscription import get_sub_url
    sub_url = get_sub_url(sub_token)

    await call.message.edit_text(
        f"<b>Подписка активирована!</b>\n\n"
        f"Действует до: <b>{expires.strftime('%d.%m.%Y')}</b>\n\n"
        f"<b>Ваша ссылка подписки:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        f"Вставьте ссылку в приложение:\n"
        f"\u2022 <b>Happ</b> (iOS/Android)\n"
        f"\u2022 <b>v2rayN</b> (Windows)\n"
        f"\u2022 <b>Hiddify</b> (все платформы)\n\n"
        f"Напомним за 3 дня до окончания.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Туториалы", callback_data="tutorials")],
            [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
        ])
    )


@router.callback_query(F.data == "my_keys")
async def my_keys(call: CallbackQuery):
    sub = await get_active_subscription(call.from_user.id)

    if not sub:
        await call.message.edit_text(
            f"<b>У вас нет активной подписки</b>\n\n"
            f"Купите VPN в главном меню.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Купить VPN", callback_data="buy_vpn")],
                [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
            ])
        )
        return

    expires = datetime.fromisoformat(sub["expires_at"])
    days_left = (expires - datetime.utcnow()).days

    from services.subscription import get_sub_url
    sub_url = get_sub_url(sub["sub_token"])

    servers = await get_active_vpn_servers()
    relays = await get_relay_servers()

    server_lines = []
    for s in servers:
        cc = s["country_code"]
        f = flag(cc)
        name = s["display_name"] or s["country_name"] or cc
        server_lines.append(f"  {f} {name}")
    for r in relays:
        cc = r["country_code"]
        f = flag(cc)
        name = r["display_name"] or "WHITELIST Relay"
        server_lines.append(f"  {f} {name} (relay)")

    servers_text = "\n".join(server_lines) if server_lines else "  \u26a0\ufe0f Нет серверов"

    from handlers.profile import fmt_bytes
    await ensure_traffic_table()
    traffic = await get_traffic(call.from_user.id)
    up = traffic.get("upload", 0)
    down = traffic.get("download", 0)
    total = up + down
    traffic_text = (
        f"\n<b>Трафик:</b> {fmt_bytes(total)}\n"
        f"  Upload: {fmt_bytes(up)} / Download: {fmt_bytes(down)}\n"
    )

    await call.message.edit_text(
        f"<b>Ваша подписка</b>\n\n"
        f"<b>Статус:</b> Активна\n"
        f"<b>До:</b> {expires.strftime('%d.%m.%Y %H:%M')} UTC ({days_left} дн.)\n"
        f"{traffic_text}\n"
        f"<b>Серверы в подписке:</b>\n"
        f"{servers_text}\n\n"
        f"<b>Ссылка подписки:</b>\n"
        f"<code>{sub_url}</code>\n\n"
        f"Скопируйте и вставьте в приложение.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Продлить (+30 дней)", callback_data="confirm_buy")],
            [InlineKeyboardButton(text="Туториалы", callback_data="tutorials")],
            [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
        ])
    )
