import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from datetime import datetime, timedelta

from database import get_expiring_subscriptions, deactivate_subscription
from database import get_all_subscriptions
from emoji import CROSS, WARNING, BELL

logger = logging.getLogger(__name__)


async def check_subscriptions(bot: Bot):
    expired = await get_expiring_subscriptions()
    for sub in expired:
        try:
            user_id = sub["user_id"]
            await deactivate_subscription(sub["id"])
            try:
                await bot.send_message(
                    user_id,
                    f"{CROSS} <b>Ваша VPN-подписка истекла!</b>\n\n"
                    f"Ключи отключены. Продлите подписку: /start",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            logger.info(f"Deactivated subscription {sub['id']} for user {user_id}")
        except Exception as ex:
            logger.error(f"Error processing expiry for sub {sub['id']}: {ex}")


async def send_expiry_warnings(bot: Bot):
    subs = await get_all_subscriptions()
    for sub in subs:
        if not sub["is_active"]:
            continue
        try:
            expires = datetime.fromisoformat(sub["expires_at"])
            days_left = (expires - datetime.utcnow()).days
            if days_left == 3:
                await bot.send_message(
                    sub["user_id"],
                    f"{WARNING} <b>Осталось 3 дня!</b>\n\n"
                    f"Подписка истекает: <b>{expires.strftime('%d.%m.%Y %H:%M')} UTC</b>\n\n"
                    f"Продлите заранее - /start",
                    parse_mode="HTML"
                )
        except Exception as ex:
            logger.error(f"Warning error for sub {sub['id']}: {ex}")


async def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_subscriptions, "interval", minutes=30, args=[bot])
    scheduler.add_job(send_expiry_warnings, "interval", hours=12, args=[bot])
    scheduler.start()
    logger.info("Scheduler started")
    return scheduler
