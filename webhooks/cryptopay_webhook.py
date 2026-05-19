import logging
import json
from aiohttp import web
from aiogram import Bot

from database import get_payment, update_payment_status, add_balance
from emoji import CHECK, ARROW_UP, MONEY

logger = logging.getLogger(__name__)


async def handle_cryptopay_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad request")

    logger.info(f"CryptoPay webhook: {json.dumps(data, default=str)}")

    update = data.get("payload", data)
    if isinstance(update, str):
        try:
            update = json.loads(update)
        except Exception:
            return web.Response(status=400)

    status = update.get("status")
    if status != "paid":
        return web.Response(text="OK")

    payload_str = update.get("payload", "")
    user_id = None
    payment_id = None

    if "|" in str(payload_str):
        for part in str(payload_str).split("|"):
            if part.startswith("uid:"):
                user_id = int(part.split(":")[1])
            elif part.startswith("pid:"):
                payment_id = part.split(":")[1]

    if not payment_id or not user_id:
        logger.error(f"CryptoPay webhook: missing uid/pid in payload: {payload_str}")
        return web.Response(status=400)

    payment = await get_payment(payment_id)
    if not payment:
        logger.error(f"Payment not found: {payment_id}")
        return web.Response(status=404)

    if payment["status"] == "paid":
        return web.Response(text="Already processed")

    await update_payment_status(payment_id, "paid")
    amount = payment["amount"]
    await add_balance(user_id, amount)

    try:
        await bot.send_message(
            user_id,
            f"{CHECK} <b>Оплата получена!</b>\n\n"
            f"{MONEY} Зачислено: <b>+{amount:.0f} \u20bd</b>\n"
            f"{ARROW_UP} Способ: CryptoBot\n\n"
            f"Теперь можете купить подписку: /start",
            parse_mode="HTML"
        )
    except Exception as ex:
        logger.error(f"Failed to notify user {user_id}: {ex}")

    return web.Response(text="OK")
