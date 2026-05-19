import logging
import json
from aiohttp import web
from aiogram import Bot

from database import get_payment, update_payment_status, add_balance
from services.lolz import verify_lolz_webhook
from emoji import CHECK, ARROW_UP, MONEY, LOLZ

logger = logging.getLogger(__name__)


async def handle_lolz_webhook(request: web.Request) -> web.Response:
    bot: Bot = request.app["bot"]

    secret = request.headers.get("x-secret-key", "")
    if not await verify_lolz_webhook(secret):
        logger.warning(f"Lolz webhook: invalid secret")
        return web.Response(status=403, text="Forbidden")

    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Bad request")

    logger.info(f"Lolz webhook: {json.dumps(data, default=str)}")

    payment_id = data.get("payment_id")
    if not payment_id:
        return web.Response(status=400, text="No payment_id")

    payment = await get_payment(str(payment_id))
    if not payment:
        logger.error(f"Lolz payment not found: {payment_id}")
        return web.Response(status=404)

    if payment["status"] == "paid":
        return web.Response(text="Already processed")

    await update_payment_status(str(payment_id), "paid")
    amount = payment["amount"]
    user_id = payment["user_id"]
    await add_balance(user_id, amount)

    try:
        await bot.send_message(
            user_id,
            f"{CHECK} <b>Оплата получена!</b>\n\n"
            f"{MONEY} Зачислено: <b>+{amount:.0f} \u20bd</b>\n"
            f"{LOLZ} Способ: Lolz.live\n\n"
            f"Теперь можете купить подписку: /start",
            parse_mode="HTML"
        )
    except Exception as ex:
        logger.error(f"Failed to notify user {user_id}: {ex}")

    return web.Response(text="OK")
