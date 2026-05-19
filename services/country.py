import aiohttp
import logging

logger = logging.getLogger(__name__)


async def detect_country(ip: str) -> dict:
    """Detect country/city by IP using free API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://ip-api.com/json/{ip}?lang=ru", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == "success":
                        return {
                            "country_code": data.get("countryCode", ""),
                            "country_name": data.get("country", ""),
                            "city": data.get("city", ""),
                            "isp": data.get("isp", ""),
                            "org": data.get("org", ""),
                        }
    except Exception as ex:
        logger.error(f"Country detection failed for {ip}: {ex}")

    return {"country_code": "", "country_name": "", "city": "", "isp": "", "org": ""}
