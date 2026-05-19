import logging
from aiohttp import web
from database import get_subscription_by_token, get_active_vpn_servers, get_relay_servers, get_server
from services.xray_manager import build_vless_link
from config import config
from emoji import flag

logger = logging.getLogger(__name__)


def get_sub_url(token: str) -> str:
    base = config.WEBHOOK_BASE_URL or f"http://0.0.0.0:{config.SUB_PORT}"
    return f"{base}/sub/{token}"


async def handle_subscription(request: web.Request) -> web.Response:
    token = request.match_info.get("token", "")
    if not token:
        return web.Response(status=404, text="Not found")

    sub = await get_subscription_by_token(token)
    if not sub:
        return web.Response(status=404, text="Subscription not found or expired")

    from datetime import datetime
    expires = datetime.fromisoformat(sub["expires_at"])
    if expires < datetime.utcnow():
        return web.Response(status=403, text="Subscription expired")

    # Get all active servers
    servers = await get_active_vpn_servers()
    relays = await get_relay_servers()

    links = []

    for s in servers:
        cc = s["country_code"]
        f = flag(cc) if cc else ""
        name = s["display_name"] or s["country_name"] or s["ip"]
        remark = f"{f} {name}".strip()

        link = build_vless_link(
            ip=s["ip"],
            port=s["xray_port"],
            uuid_val=s["xray_uuid"],
            public_key=s["xray_public_key"],
            short_id=s["xray_short_id"],
            sni=s["xray_sni"],
            remark=remark
        )
        links.append(link)

    for r in relays:
        target = await get_server(r["relay_target_id"]) if r["relay_target_id"] else None
        if not target or not target["xray_uuid"]:
            continue

        cc = r["country_code"]
        f = flag(cc) if cc else ""
        name = r["display_name"] or f"WHITELIST {r['country_name']}"
        remark = f"{f} {name}".strip()

        # Relay: use relay IP but target's Xray credentials
        link = build_vless_link(
            ip=r["ip"],
            port=target["xray_port"],
            uuid_val=target["xray_uuid"],
            public_key=target["xray_public_key"],
            short_id=target["xray_short_id"],
            sni=target["xray_sni"],
            remark=remark
        )
        links.append(link)

    if not links:
        return web.Response(status=503, text="No servers available")

    import base64
    body = "\n".join(links)
    encoded = base64.b64encode(body.encode()).decode()

    # Get real traffic stats from database
    from database import get_traffic
    traffic = await get_traffic(sub["user_id"])
    upload_bytes = traffic.get("upload", 0)
    download_bytes = traffic.get("download", 0)

    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "Subscription-Userinfo": f"upload={upload_bytes}; download={download_bytes}; total=0; expire={int(expires.timestamp())}",
        "Content-Disposition": f'attachment; filename="vpn_sub"',
        "Profile-Update-Interval": "12",
        "Profile-Title": "Premium VPN",
    }

    return web.Response(text=encoded, headers=headers)


def create_sub_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/sub/{token}", handle_subscription)
    return app
