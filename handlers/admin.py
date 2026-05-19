import logging
import os
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                            InlineKeyboardButton)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (get_all_users, get_all_subscriptions, get_active_sub_count,
                       get_user_count, get_total_revenue, get_all_servers,
                       add_server, delete_server, toggle_server, update_server_xray,
                       get_server, add_balance)
from services.country import detect_country
from services.xray_manager import setup_server_full, setup_relay, check_server_alive
from config import config
from emoji import STATS, WARNING, BELL, MESSAGE, CROSS, CHECK, GLOBE, SHIELD, ROCKET, KEY

logger = logging.getLogger(__name__)
router = Router()


class AddServerState(StatesGroup):
    waiting_ip = State()
    waiting_user = State()
    waiting_password = State()
    waiting_port = State()


class AddRelayState(StatesGroup):
    waiting_ip = State()
    waiting_user = State()
    waiting_password = State()
    waiting_target = State()


class BroadcastState(StatesGroup):
    waiting_message = State()


class AddBalanceState(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


def _admin_panel_url() -> str:
    base = config.WEBHOOK_BASE_URL
    if base:
        return f"{base.rstrip('/')}/admin/"
    return ""


def admin_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Пароль админки", callback_data="adm_password")],
    ]
    url = _admin_panel_url()
    if url:
        buttons.append([InlineKeyboardButton(text="Открыть веб-панель", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


class SetPasswordState(StatesGroup):
    waiting_password = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not config.is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.")
        return

    users = await get_user_count()
    subs = await get_active_sub_count()
    revenue = await get_total_revenue()

    url = _admin_panel_url()
    panel_line = f"\nВеб-панель: {url}" if url else ""
    pwd_line = f"\nПароль: <tg-spoiler>{config.ADMIN_PASSWORD}</tg-spoiler>"

    await message.answer(
        f"<b>Панель администратора</b>\n\n"
        f"Пользователей: <b>{users}</b>\n"
        f"Активных подписок: <b>{subs}</b>\n"
        f"Доход: <b>{revenue:.0f} \u20bd</b>"
        f"{panel_line}{pwd_line}",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )


@router.callback_query(F.data == "adm_back")
async def adm_back(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    users = await get_user_count()
    subs = await get_active_sub_count()
    revenue = await get_total_revenue()
    await call.message.edit_text(
        f"<b>Панель администратора</b>\n\n"
        f"Пользователей: <b>{users}</b>\n"
        f"Активных подписок: <b>{subs}</b>\n"
        f"Доход: <b>{revenue:.0f} \u20bd</b>",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )


@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    users = await get_user_count()
    subs = await get_active_sub_count()
    revenue = await get_total_revenue()
    from database import get_all_servers
    servers = await get_all_servers()
    active_servers = [s for s in servers if s["is_active"]]

    await call.message.edit_text(
        f"<b>Подробная статистика</b>\n\n"
        f"Пользователей: <b>{users}</b>\n"
        f"Активных подписок: <b>{subs}</b>\n"
        f"Доход: <b>{revenue:.0f} \u20bd</b>\n"
        f"Серверов: <b>{len(active_servers)}/{len(servers)}</b>\n"
        f"Цена подписки: <b>{config.PRICE_RUB} \u20bd</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="adm_back")]
        ])
    )


# ─── Servers management ─────────────────────────────────────────────────

@router.callback_query(F.data == "adm_servers")
async def adm_servers(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    servers = await get_all_servers()

    lines = [f"<b>Серверы ({len(servers)})</b>\n"]
    for s in servers:
        from emoji import flag
        f = flag(s["country_code"]) if s["country_code"] else "\U0001f3f3\ufe0f"
        status = "\U0001f7e2" if s["is_active"] else "\U0001f534"
        relay = " [RELAY]" if s["is_relay"] else ""
        name = s["display_name"] or s["country_name"] or s["ip"]
        xray = "\u2705" if s["xray_uuid"] else "\u274c"
        lines.append(f"{status} {f} <b>{name}</b>{relay}\n   {s['ip']} | Xray: {xray}")

    buttons = [
        [InlineKeyboardButton(text="Добавить VPN сервер", callback_data="adm_add_server")],
        [InlineKeyboardButton(text="Добавить Relay (whitelist)", callback_data="adm_add_relay")],
    ]

    for s in servers:
        f = ""
        if s["country_code"]:
            from emoji import flag
            f = flag(s["country_code"]) + " "
        name = s["display_name"] or s["ip"]
        buttons.append([
            InlineKeyboardButton(text=f"{f}{name}", callback_data=f"adm_srv:{s['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="Назад", callback_data="adm_back")])

    await call.message.edit_text(
        "\n".join(lines) if servers else f"{GLOBE} <b>Серверы</b>\n\nПока нет серверов.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("adm_srv:"))
async def adm_server_detail(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    server_id = int(call.data.split(":")[1])
    s = await get_server(server_id)
    if not s:
        await call.answer("Сервер не найден", show_alert=True)
        return

    from emoji import flag
    f = flag(s["country_code"]) if s["country_code"] else ""
    status = "\U0001f7e2 Активен" if s["is_active"] else "\U0001f534 Отключён"
    xray_status = "\u2705 Настроен" if s["xray_uuid"] else "\u274c Не настроен"
    relay = "\U0001f504 Relay" if s["is_relay"] else "\U0001f310 VPN"

    text = (
        f"{f} <b>{s['display_name'] or s['ip']}</b>\n\n"
        f"IP: <code>{s['ip']}</code>\n"
        f"SSH: {s['ssh_user']}@{s['ip']}:{s['ssh_port']}\n"
        f"Тип: {relay}\n"
        f"Статус: {status}\n"
        f"Xray: {xray_status}\n"
        f"Страна: {s['country_name']} ({s['country_code']})\n"
        f"Город: {s['city']}\n"
        f"Скорость: {s['speed']}\n"
    )

    if s["xray_uuid"]:
        text += f"\nUUID: <code>{s['xray_uuid']}</code>\n"
        text += f"Port: {s['xray_port']}\n"
        text += f"SNI: {s['xray_sni']}\n"

    buttons = []
    if not s["xray_uuid"] and not s["is_relay"]:
        buttons.append([InlineKeyboardButton(text="Установить Xray", callback_data=f"adm_setup_xray:{server_id}")])
    if s["is_active"]:
        buttons.append([InlineKeyboardButton(text="Отключить", callback_data=f"adm_toggle:{server_id}:0")])
    else:
        buttons.append([InlineKeyboardButton(text="Включить", callback_data=f"adm_toggle:{server_id}:1")])
    buttons.append([InlineKeyboardButton(text="Удалить", callback_data=f"adm_del_srv:{server_id}")])
    buttons.append([InlineKeyboardButton(text="Серверы", callback_data="adm_servers")])

    await call.message.edit_text(text, parse_mode="HTML",
                                  reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("adm_toggle:"))
async def adm_toggle(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    parts = call.data.split(":")
    server_id = int(parts[1])
    active = bool(int(parts[2]))
    await toggle_server(server_id, active)
    await call.answer(f"{'Включён' if active else 'Отключён'}", show_alert=True)
    await adm_server_detail(call)


@router.callback_query(F.data.startswith("adm_del_srv:"))
async def adm_del_srv(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    server_id = int(call.data.split(":")[1])
    await delete_server(server_id)
    await call.answer("\U0001f5d1\ufe0f Сервер удалён", show_alert=True)
    await adm_servers(call)


# ─── Add VPN server flow ────────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_server")
async def adm_add_server_start(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        f"<b>Добавление VPN сервера</b>\n\n"
        f"Введите IP-адрес сервера:",
        parse_mode="HTML"
    )
    await state.set_state(AddServerState.waiting_ip)
    await state.update_data(is_relay=False)


@router.message(AddServerState.waiting_ip)
async def add_server_ip(message: Message, state: FSMContext):
    ip = message.text.strip()
    await state.update_data(ip=ip)
    await message.answer(
        f"IP: <code>{ip}</code>\n\n"
        f"Введите SSH логин (по умолчанию root):",
        parse_mode="HTML"
    )
    await state.set_state(AddServerState.waiting_user)


@router.message(AddServerState.waiting_user)
async def add_server_user(message: Message, state: FSMContext):
    user = message.text.strip() or "root"
    await state.update_data(ssh_user=user)
    await message.answer(f"Логин: {user}\n\nВведите SSH пароль:")
    await state.set_state(AddServerState.waiting_password)


@router.message(AddServerState.waiting_password)
async def add_server_password(message: Message, state: FSMContext, bot: Bot):
    password = message.text.strip()
    data = await state.get_data()
    await state.clear()

    ip = data["ip"]
    ssh_user = data["ssh_user"]
    is_relay = data.get("is_relay", False)

    # Delete password message for security
    try:
        await message.delete()
    except Exception:
        pass

    status_msg = await message.answer(
        f"\U0001f50d <b>Определяю страну...</b>\n\nIP: {ip}",
        parse_mode="HTML"
    )

    # Detect country
    geo = await detect_country(ip)
    cc = geo["country_code"]
    country = geo["country_name"]
    city = geo["city"]

    from emoji import flag
    f = flag(cc) if cc else "\U0001f3f3\ufe0f"
    display_name = f"{country}" + (f", {city}" if city else "")

    if is_relay:
        target_id = data.get("relay_target_id")
        # Build display: WHITELIST 🇷🇺 → 🇩🇪
        target = await get_server(target_id) if target_id else None
        target_flag = flag(target["country_code"]) if target and target.get("country_code") else ""
        relay_display = f"WHITELIST {f} → {target_flag}".strip()

        server_id = await add_server(
            ip=ip, ssh_user=ssh_user, ssh_password=password, ssh_port=22,
            country_code=cc, country_name=country, city=city,
            display_name=relay_display,
            is_relay=1, relay_target_id=target_id
        )

        # Setup relay
        if target:
            await status_msg.edit_text(
                f"\U0001f504 <b>Настраиваю relay...</b>\n\n"
                f"{f} {ip} \u2192 {target['ip']}:{target['xray_port']}",
                parse_mode="HTML"
            )
            ok = await setup_relay(ip, ssh_user, password, target["ip"], target["xray_port"])
            if ok:
                await status_msg.edit_text(
                    f"{CHECK} <b>Relay сервер добавлен!</b>\n\n"
                    f"{f} {display_name}\n"
                    f"IP: <code>{ip}</code>\n"
                    f"\U0001f504 \u2192 {target['ip']}",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="\u25c0\ufe0f Серверы", callback_data="adm_servers")]
                    ])
                )
            else:
                await status_msg.edit_text(
                    f"{CROSS} <b>Ошибка настройки relay</b>\n\n"
                    f"Сервер добавлен в БД, но relay не настроен.\n"
                    f"Проверьте SSH доступ и повторите.",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="\u25c0\ufe0f Серверы", callback_data="adm_servers")]
                    ])
                )
        return

    # Add VPN server to DB
    server_id = await add_server(
        ip=ip, ssh_user=ssh_user, ssh_password=password, ssh_port=22,
        country_code=cc, country_name=country, city=city,
        display_name=display_name
    )

    await status_msg.edit_text(
        f"\U0001f680 <b>Устанавливаю Xray на сервер...</b>\n\n"
        f"{f} {display_name}\n"
        f"IP: {ip}\n\n"
        f"Это займёт 1-3 минуты...",
        parse_mode="HTML"
    )

    # Full auto-setup
    result = await setup_server_full(ip, ssh_user, password)

    if "error" in result:
        await status_msg.edit_text(
            f"{CROSS} <b>Ошибка установки!</b>\n\n"
            f"{result['error']}\n\n"
            f"Сервер добавлен в БД. Можно попробовать установить Xray позже.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="\U0001f680 Попробовать снова", callback_data=f"adm_setup_xray:{server_id}")],
                [InlineKeyboardButton(text="\u25c0\ufe0f Серверы", callback_data="adm_servers")]
            ])
        )
        return

    # Save Xray keys to DB
    await update_server_xray(
        server_id,
        uuid_val=result["uuid"],
        private_key=result["private_key"],
        public_key=result["public_key"],
        short_id=result["short_id"],
        xray_port=result["port"],
        sni=result["sni"]
    )

    await status_msg.edit_text(
        f"{CHECK} <b>Сервер добавлен и настроен!</b>\n\n"
        f"{f} <b>{display_name}</b>\n"
        f"IP: <code>{ip}</code>\n"
        f"Xray: \u2705 Установлен\n"
        f"Port: {result['port']}\n"
        f"UUID: <code>{result['uuid']}</code>\n\n"
        f"Сервер автоматически добавлен в подписку.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f Серверы", callback_data="adm_servers")]
        ])
    )


@router.callback_query(F.data.startswith("adm_setup_xray:"))
async def adm_setup_xray(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    server_id = int(call.data.split(":")[1])
    s = await get_server(server_id)
    if not s:
        await call.answer("Сервер не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"<b>Устанавливаю Xray...</b>\n\n"
        f"IP: {s['ip']}\nЭто займёт 1-3 минуты...",
        parse_mode="HTML"
    )

    result = await setup_server_full(s["ip"], s["ssh_user"], s["ssh_password"], s["ssh_port"])

    if "error" in result:
        await call.message.edit_text(
            f"{CROSS} <b>Ошибка: {result['error']}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Повторить", callback_data=f"adm_setup_xray:{server_id}")],
                [InlineKeyboardButton(text="Серверы", callback_data="adm_servers")]
            ])
        )
        return

    await update_server_xray(
        server_id,
        uuid_val=result["uuid"],
        private_key=result["private_key"],
        public_key=result["public_key"],
        short_id=result["short_id"],
        xray_port=result["port"],
        sni=result["sni"]
    )

    await call.message.edit_text(
        f"{CHECK} <b>Xray установлен!</b>\n\n"
        f"UUID: <code>{result['uuid']}</code>\n"
        f"Port: {result['port']}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Серверы", callback_data="adm_servers")]
        ])
    )


# ─── Add Relay server flow ──────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_relay")
async def adm_add_relay_start(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return

    servers = await get_all_servers()
    vpn_servers = [s for s in servers if not s["is_relay"] and s["xray_uuid"]]

    if not vpn_servers:
        await call.answer("\u26a0\ufe0f Сначала добавьте VPN сервер", show_alert=True)
        return

    buttons = []
    for s in vpn_servers:
        from emoji import flag
        f = flag(s["country_code"]) if s["country_code"] else ""
        name = s["display_name"] or s["ip"]
        buttons.append([InlineKeyboardButton(
            text=f"{f} {name}", callback_data=f"adm_relay_target:{s['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="adm_servers")])

    await call.message.edit_text(
        f"<b>Добавление Relay сервера</b>\n\n"
        f"Relay перенаправляет трафик через российский IP (белый список) "
        f"на VPN сервер за рубежом.\n\n"
        f"Выберите целевой VPN сервер:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("adm_relay_target:"))
async def adm_relay_target(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[1])
    await state.update_data(is_relay=True, relay_target_id=target_id)
    await call.message.edit_text(
        f"<b>Relay сервер</b>\n\n"
        f"Введите IP российского сервера (с белым списком):",
        parse_mode="HTML"
    )
    await state.set_state(AddServerState.waiting_ip)


# ─── Users ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_users")
async def adm_users(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    users = await get_all_users()

    lines = [f"<b>Пользователи ({len(users)})</b>\n"]
    for u in list(users)[:30]:
        name = u["first_name"] or "\u2014"
        uname = f"@{u['username']}" if u["username"] else "\u2014"
        lines.append(f"\u2022 <code>{u['user_id']}</code> {name} {uname} | {u['balance']:.0f}\u20bd")

    if len(users) > 30:
        lines.append(f"\n... \u0438 \u0435\u0449\u0451 {len(users)-30}")

    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="adm_back")]
        ])
    )


# ─── Subscriptions ───────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_subs")
async def adm_subs(call: CallbackQuery):
    if not config.is_admin(call.from_user.id):
        return
    from datetime import datetime
    subs = await get_all_subscriptions()
    active = [s for s in subs if s["is_active"]]

    lines = [f"<b>Активные подписки ({len(active)})</b>\n"]
    for s in list(active)[:20]:
        name = s["first_name"] or "\u2014"
        expires = s["expires_at"][:10]
        days = (datetime.fromisoformat(s["expires_at"]) - datetime.utcnow()).days
        lines.append(f"\u2022 <code>{s['user_id']}</code> {name} \u00b7 {expires} ({days}\u0434)")

    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="adm_back")]
        ])
    )


# ─── Broadcast ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        f"<b>Рассылка</b>\n\n"
        f"Отправьте сообщение для рассылки.\n"
        f"Поддерживается: текст, фото, видео.\n\n"
        f"Для отмены: /admin",
        parse_mode="HTML"
    )
    await state.set_state(BroadcastState.waiting_message)


@router.message(BroadcastState.waiting_message)
async def do_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    await state.clear()
    users = await get_all_users()
    sent = 0
    failed = 0

    status_msg = await message.answer(
        f"{BELL} Рассылка... 0/{len(users)}",
        parse_mode="HTML"
    )

    for i, user in enumerate(users):
        try:
            await bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            sent += 1
        except Exception:
            failed += 1

        if (i + 1) % 20 == 0:
            try:
                await status_msg.edit_text(f"{BELL} Рассылка... {i+1}/{len(users)}")
            except Exception:
                pass

    await status_msg.edit_text(
        f"{CHECK} <b>Рассылка завершена!</b>\n\n"
        f"\u2705 Отправлено: <b>{sent}</b>\n"
        f"{CROSS} Ошибок: <b>{failed}</b>",
        parse_mode="HTML"
    )


# ─── Add balance to user ────────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_balance")
async def adm_add_balance_start(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    await call.message.edit_text(
        f"<b>Начислить баланс</b>\n\n"
        f"Введите Telegram ID пользователя:",
        parse_mode="HTML"
    )
    await state.set_state(AddBalanceState.waiting_user_id)


@router.message(AddBalanceState.waiting_user_id)
async def add_balance_uid(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID")
        return
    await state.update_data(target_uid=uid)
    await message.answer(f"ID: {uid}\n\nВведите сумму в рублях:")
    await state.set_state(AddBalanceState.waiting_amount)


@router.message(AddBalanceState.waiting_amount)
async def add_balance_amount(message: Message, state: FSMContext, bot: Bot):
    if not config.is_admin(message.from_user.id):
        return
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("Введите число")
        return

    data = await state.get_data()
    await state.clear()
    uid = data["target_uid"]

    await add_balance(uid, amount)
    await message.answer(
        f"{CHECK} Начислено <b>{amount:.0f} \u20bd</b> пользователю <code>{uid}</code>",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            uid,
            f"<b>Баланс пополнен!</b>\n\n"
            f"Зачислено: <b>+{amount:.0f} \u20bd</b>\n"
            f"Способ: начисление администратором",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ——— Admin password management ———

@router.callback_query(F.data == "adm_password")
async def adm_password_show(call: CallbackQuery, state: FSMContext):
    if not config.is_admin(call.from_user.id):
        return
    url = _admin_panel_url()
    panel_line = f"\nВеб-панель: {url}" if url else ""
    await call.message.edit_text(
        f"<b>Пароль админ-панели</b>\n\n"
        f"Текущий пароль: <tg-spoiler>{config.ADMIN_PASSWORD}</tg-spoiler>"
        f"{panel_line}\n\n"
        f"Отправьте новый пароль или нажмите Назад.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="adm_back")]
        ])
    )
    await state.set_state(SetPasswordState.waiting_password)


@router.message(SetPasswordState.waiting_password)
async def set_admin_password(message: Message, state: FSMContext):
    if not config.is_admin(message.from_user.id):
        return
    new_pwd = message.text.strip()
    if len(new_pwd) < 4:
        await message.answer("Пароль слишком короткий (мин. 4 символа). Попробуйте ещё раз.")
        return

    config.ADMIN_PASSWORD = new_pwd
    await state.clear()

    # Persist to .env file
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("ADMIN_PASSWORD="):
                        lines.append(f"ADMIN_PASSWORD={new_pwd}\n")
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f"ADMIN_PASSWORD={new_pwd}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
    except Exception as e:
        logger.warning(f"Could not update .env: {e}")

    # Try to delete password message for security
    try:
        await message.delete()
    except Exception:
        pass

    await message.answer(
        f"Пароль изменён.\n\n"
        f"Новый пароль: <tg-spoiler>{new_pwd}</tg-spoiler>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Назад", callback_data="adm_back")]
        ])
    )
