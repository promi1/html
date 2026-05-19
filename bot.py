import asyncio
import logging
import sys
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import config
from database import init_db
from services.scheduler import start_scheduler
from services.subscription import create_sub_app
from webhooks.cryptopay_webhook import handle_cryptopay_webhook
from webhooks.lolz_webhook import handle_lolz_webhook
from web.app import create_web_app

from handlers import start, subscription, payment, admin, profile, tutorials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    logger.info("Bot starting up...")
    await init_db()
    start_scheduler(bot)
    me = await bot.get_me()
    logger.info(f"Bot @{me.username} (id={me.id}) started")


async def main():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN not set in .env")
        sys.exit(1)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Register routers
    dp.include_router(start.router)
    dp.include_router(subscription.router)
    dp.include_router(payment.router)
    dp.include_router(profile.router)
    dp.include_router(tutorials.router)
    dp.include_router(admin.router)

    # Startup hook
    dp.startup.register(on_startup)

    # --- HTTP server for webhooks + subscription + web admin ---
    app = web.Application()
    app["bot"] = bot

    # Payment webhooks
    app.router.add_post("/webhook/cryptopay", handle_cryptopay_webhook)
    app.router.add_post("/webhook/lolz", handle_lolz_webhook)

    # Subscription endpoint
    sub_app = create_sub_app()
    app.add_subapp("/", sub_app)

    # Web admin panel
    web_app = create_web_app()
    for route in web_app.router.routes():
        resource = route.resource
        if resource is not None:
            info = resource.get_info()
            if "formatter" in info:
                path = info["formatter"]
            elif "path" in info:
                path = info["path"]
            else:
                continue
            # Re-register route on main app
            if hasattr(route, "method") and route.method == "POST":
                app.router.add_post(path, route.handler)
            elif hasattr(route, "method"):
                app.router.add_get(path, route.handler)

    # Serve static files for admin panel
    import os
    static_dir = os.path.join(os.path.dirname(__file__), "web", "static")
    if os.path.exists(static_dir):
        app.router.add_static("/static", static_dir, name="static")

    # Setup jinja2 on main app too
    import aiohttp_jinja2
    import jinja2
    templates_dir = os.path.join(os.path.dirname(__file__), "web", "templates")
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(templates_dir))

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.WEBHOOK_PORT)
    await site.start()
    logger.info(f"HTTP server started on port {config.WEBHOOK_PORT}")
    logger.info(f"  Subscription: http://0.0.0.0:{config.WEBHOOK_PORT}/sub/TOKEN")
    logger.info(f"  Admin panel:  http://0.0.0.0:{config.WEBHOOK_PORT}/admin/")
    logger.info(f"  CryptoPay WH: http://0.0.0.0:{config.WEBHOOK_PORT}/webhook/cryptopay")
    logger.info(f"  Lolz WH:      http://0.0.0.0:{config.WEBHOOK_PORT}/webhook/lolz")

    # Start polling
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
