import logging
import os
import shutil
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import FSInputFile
from datetime import datetime, timedelta

from database import (get_expiring_subscriptions, deactivate_subscription,
                      get_all_subscriptions, get_active_servers,
                      ensure_traffic_table, update_traffic)
from config import config
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
    """Query Xray stats from all active servers and update traffic DB.
    Uses -reset flag for incremental collection. Traffic is split evenly among active users.
    """
    from services.xray_manager import query_xray_stats
    await ensure_traffic_table()
    servers = await get_active_servers()
    total_up = 0
    total_down = 0
    for s in servers:
        if not s["xray_uuid"]:
            continue
        try:
            s_dict = dict(s) if not isinstance(s, dict) else s
            ssh_key = s_dict.get("ssh_key", "") or ""
            stats = await query_xray_stats(
                s["ip"], s["ssh_user"], s["ssh_password"],
                s["ssh_port"], ssh_key=ssh_key
            )
            up = stats.get("uplink", 0)
            down = stats.get("downlink", 0)
            if up > 0 or down > 0:
                total_up += up
                total_down += down
                logger.info(f"Traffic from {s['ip']}: up={up}, down={down}")
        except Exception as e:
            logger.warning(f"Traffic sync failed for {s['ip']}: {e}")

    if total_up > 0 or total_down > 0:
        subs = await get_all_subscriptions()
        active_users = [sub["user_id"] for sub in subs if sub["is_active"]]
        n = max(len(active_users), 1)
        for uid in active_users:
            await update_traffic(uid, total_up // n, total_down // n)
        logger.info(f"Traffic distributed to {len(active_users)} users: up={total_up}, down={total_down}")


async def send_db_backup(bot: Bot):
    """Send database backup to all admin users via Telegram."""
    try:
        db_path = config.DB_PATH
        if not os.path.exists(db_path):
            logger.warning("DB backup: database file not found")
            return
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
        backup_name = f"vpnbot_backup_{timestamp}.db"
        backup_path = f"/tmp/{backup_name}"
        shutil.copy2(db_path, backup_path)
        admin_ids = config.ADMIN_IDS
        for admin_id in admin_ids:
            try:
                doc = FSInputFile(backup_path, filename=backup_name)
                await bot.send_document(
                    admin_id, doc,
                    caption=f"🗄 Бэкап базы данных\n📅 {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC"
                )
            except Exception as ex:
                logger.error(f"Failed to send backup to admin {admin_id}: {ex}")
        os.remove(backup_path)
        logger.info(f"DB backup sent to {len(admin_ids)} admins")
    except Exception as e:
        logger.error(f"DB backup failed: {e}")


async def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_subscriptions, "interval", minutes=30, args=[bot])
    scheduler.add_job(send_expiry_warnings, "interval", hours=12, args=[bot])
    scheduler.add_job(sync_traffic, "interval", seconds=40)
    scheduler.add_job(send_db_backup, "interval", hours=3, args=[bot])
    scheduler.start()
    logger.info("Scheduler started (sub check: 30m, warnings: 12h, traffic: 40s, backup: 3h)")
    return scheduler
