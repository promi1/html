import aiohttp
import logging
from config import config

logger = logging.getLogger(__name__)

LOLZ_API = "https://prod-api.lzt.market"


async def create_lolz_invoice(user_id: int, rub_amount: float, payment_id: str,
                               callback_url: str, success_url: str) -> dict | None:
    if not config.LOLZ_TOKEN:
        logger.warning("Lolz token not configured")
        return None
    headers = {
        "Authorization": f"Bearer {config.LOLZ_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "currency": "rub",
        "amount": rub_amount,
        "payment_id": payment_id,
        "comment": f"VPN | TG ID: {user_id}",
        "url_success": success_url,
        "url_callback": callback_url,
        "merchant_id": config.LOLZ_MERCHANT_ID,
        "required_telegram_id": user_id,
        "lifetime": 3600,
        "additional_data": f'{{"user_id": {user_id}}}',
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{LOLZ_API}/invoice", json=payload, headers=headers) as resp:
                data = await resp.json()
                if resp.status == 200 and "invoice" in data:
                    return data["invoice"]
                logger.error(f"Lolz invoice error {resp.status}: {data}")
                return None
    except Exception as ex:
        logger.error(f"Lolz request error: {ex}")
        return None


async def verify_lolz_webhook(secret_key: str) -> bool:
    return secret_key == config.LOLZ_MERCHANT_TOKEN
