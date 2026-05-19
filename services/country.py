import aiohttp
import logging

logger = logging.getLogger(__name__)


async def detect_country(ip: str) -> dict:
    """Detect country/city by IP using free APIs with fallback."""
    empty = {"country_code": "", "country_name": "", "city": "", "isp": "", "org": ""}
    apis = [
        (f"http://ip-api.com/json/{ip}?lang=ru", _parse_ip_api),
        (f"https://api.2ip.ua/geo.json?ip={ip}", _parse_2ip),
        (f"https://ipwho.is/{ip}", _parse_ipwhois),
    ]
    try:
        async with aiohttp.ClientSession() as session:
            for url, parser in apis:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            result = parser(data)
                            if result and result.get("country_code"):
                                return result
                except Exception:
                    continue
    except Exception as ex:
        logger.error(f"Country detection failed for {ip}: {ex}")
    return empty


def _parse_2ip(data: dict) -> dict:
    cc = data.get("country_code", "")
    if cc:
        return {
            "country_code": cc,
            "country_name": data.get("country_rus", "") or data.get("country", ""),
            "city": data.get("city_rus", "") or data.get("city", ""),
            "isp": "",
            "org": "",
        }
    return {}


def _parse_ip_api(data: dict) -> dict:
    if data.get("status") == "success":
        return {
            "country_code": data.get("countryCode", ""),
            "country_name": data.get("country", ""),
            "city": data.get("city", ""),
            "isp": data.get("isp", ""),
            "org": data.get("org", ""),
        }
    return {}


def _parse_ipwhois(data: dict) -> dict:
    if data.get("success"):
        return {
            "country_code": data.get("country_code", ""),
            "country_name": data.get("country", ""),
            "city": data.get("city", ""),
            "isp": data.get("connection", {}).get("isp", ""),
            "org": data.get("connection", {}).get("org", ""),
        }
    return {}
