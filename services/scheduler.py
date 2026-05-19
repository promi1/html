import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from datetime import datetime, timedelta

from database import (get_expiring_subscriptions, deactivate_subscription,
                      get_all_subscriptions, get_active_servers,
                      ensure_traffic_table, update_traffic)
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


async def sync_traffic():
    """Query Xray stats from all active servers and update traffic DB."""
    from services.xray_manager import query_xray_stats
    await ensure_traffic_table()
    servers = await get_active_servers()
    for s in servers:
        if not s["xray_uuid"]:
            continue
        try:
            email = f"user-{s['xray_uuid'][:8]}"
            stats = await query_xray_stats(
                s["ip"], s["ssh_user"], s["ssh_password"],
                s["ssh_port"], ssh_key="", email=email
            )
            if stats and (stats.get("uplink", 0) > 0 or stats.get("downlink", 0) > 0):
                from database import get_all_subscriptions
                subs = await get_all_subscriptions()
                active_users = [sub["user_id"] for sub in subs if sub["is_active"]]
                for uid in active_users:
                    up = stats.get("uplink", 0) // max(len(active_users), 1)
                    down = stats.get("downlink", 0) // max(len(active_users), 1)
                    if up > 0 or down > 0:
                        await update_traffic(uid, up, down)
                logger.info(f"Traffic synced from {s['ip']}: up={stats.get('uplink',0)}, down={stats.get('downlink',0)}")
        except Exception as e:
            logger.warning(f"Traffic sync failed for {s['ip']}: {e}")


async def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_subscriptions, "interval", minutes=30, args=[bot])
    scheduler.add_job(send_expiry_warnings, "interval", hours=12, args=[bot])
    scheduler.add_job(sync_traffic, "interval", minutes=10)
    scheduler.start()
    logger.info("Scheduler started (sub check: 30m, warnings: 12h, traffic sync: 10m)")
    return scheduler
