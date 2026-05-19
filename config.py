import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: list = field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()
    ])

    # Channel subscription check
    CHANNEL_ID: str = os.getenv("CHANNEL_ID", "")  # e.g. @yourchannel or -100xxxxx
    CHANNEL_URL: str = os.getenv("CHANNEL_URL", "")  # https://t.me/yourchannel

    # CryptoBot
    CRYPTOPAY_TOKEN: str = os.getenv("CRYPTOPAY_TOKEN", "")

    # Lolz
    LOLZ_TOKEN: str = os.getenv("LOLZ_TOKEN", "")
    LOLZ_MERCHANT_ID: int = int(os.getenv("LOLZ_MERCHANT_ID", "0"))
    LOLZ_MERCHANT_TOKEN: str = os.getenv("LOLZ_MERCHANT_TOKEN", "")

    # Web admin panel
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-to-random-string")

    # Webhook
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8080"))
    WEB_PORT: int = int(os.getenv("WEB_PORT", "8443"))
    WEBHOOK_BASE_URL: str = os.getenv("WEBHOOK_BASE_URL", "")

    # Pricing
    PRICE_RUB: int = int(os.getenv("PRICE_RUB", "119"))

    # DB
    DB_PATH: str = os.getenv("DB_PATH", "/opt/vpnbot/vpnbot.db")

    # Subscription
    SUB_PORT: int = int(os.getenv("SUB_PORT", "8880"))

    # telegra.ph
    RULES_URL: str = os.getenv("RULES_URL", "")
    TUTORIAL_URL: str = os.getenv("TUTORIAL_URL", "")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.ADMIN_IDS


config = Config()
