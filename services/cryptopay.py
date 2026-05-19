import logging
from config import config

logger = logging.getLogger(__name__)

RUB_RATES = {
    "USDT": 90,
    "TON": 400,
    "TRX": 12,
    "BTC": 8000000,
}


async def get_crypto_amount(rub_amount: float, currency: str) -> float:
    rate = RUB_RATES.get(currency, 90)
    amount = rub_amount / rate
    if currency == "BTC":
        return round(amount, 8)
    elif currency == "USDT":
        return round(amount, 2)
    return round(amount, 4)


async def create_crypto_invoice(user_id: int, rub_amount: float, currency: str,
                                 payment_id: str, description: str = "VPN"):
    if not config.CRYPTOPAY_TOKEN:
        logger.warning("CryptoBot token not configured")
        return None
    try:
        from aiosend import CryptoPay
        cp = CryptoPay(token=config.CRYPTOPAY_TOKEN)
        amount = await get_crypto_amount(rub_amount, currency)
        invoice = await cp.create_invoice(
            amount=amount,
            asset=currency,
            description=description,
            payload=f"uid:{user_id}|pid:{payment_id}",
            allow_comments=False,
            allow_anonymous=True,
            expires_in=3600,
        )
        return invoice
    except Exception as ex:
        logger.error(f"CryptoPay invoice error: {ex}")
        return None
