import csv
import io
import logging
import os
from aiohttp import web
import aiohttp_jinja2
import jinja2
from config import config
from database import (get_all_servers, get_server, get_all_users, get_user_count,
                       get_active_sub_count, get_total_revenue, get_all_subscriptions,
                       add_server, delete_server, toggle_server, update_server_xray,
                       get_user, add_balance, search_users, get_user_total_payments,
                       get_all_users_with_payments, get_all_traffic, ensure_traffic_table)
from services.country import detect_country
from services.xray_manager import setup_server_full, setup_relay, check_server_alive
from emoji import flag

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Simple session store
sessions = {}


def check_auth(request):
    token = request.cookies.get("admin_token", "")
    return token in sessions and sessions[token]


@aiohttp_jinja2.template("login.html")
async def login_page(request):
    if check_auth(request):
        raise web.HTTPFound("/admin/dashboard")
    return {"error": ""}


async def login_post(request):
    data = await request.post()
    password = data.get("password", "")
    if password == config.ADMIN_PASSWORD:
        import secrets
        token = secrets.token_hex(32)
        sessions[token] = True
        resp = web.HTTPFound("/admin/dashboard")
        resp.set_cookie("admin_token", token, max_age=86400, httponly=True)
        return resp
    return aiohttp_jinja2.render_template("login.html", request, {"error": "Неверный пароль"})


async def logout(request):
    token = request.cookies.get("admin_token", "")
    sessions.pop(token, None)
    resp = web.HTTPFound("/admin/login")
    resp.del_cookie("admin_token")
    return resp


@aiohttp_jinja2.template("dashboard.html")
async def dashboard(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    users = await get_user_count()
    subs = await get_active_sub_count()
    revenue = await get_total_revenue()
    servers = await get_all_servers()
    active_servers = [s for s in servers if s["is_active"]]
    return {
        "users": users,
        "subs": subs,
        "revenue": revenue,
        "servers": len(servers),
        "active_servers": len(active_servers),
        "price": config.PRICE_RUB,
    }


@aiohttp_jinja2.template("servers.html")
async def servers_page(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    servers = await get_all_servers()
    server_list = []
    for s in servers:
        server_list.append({
            "id": s["id"],
            "ip": s["ip"],
            "country_code": s["country_code"],
            "country_name": s["country_name"],
            "city": s["city"],
            "display_name": s["display_name"],
            "is_active": s["is_active"],
            "is_relay": s["is_relay"],
            "xray_configured": bool(s["xray_uuid"]),
            "speed": s["speed"],
            "flag": flag(s["country_code"]) if s["country_code"] else "\U0001f3f3\ufe0f",
        })
    return {"servers": server_list}


@aiohttp_jinja2.template("add_server.html")
async def add_server_page(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    servers = await get_all_servers()
    vpn_servers = [s for s in servers if not s["is_relay"] and s["xray_uuid"]]
    return {"vpn_servers": vpn_servers, "error": "", "success": ""}


async def add_server_post(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    data = await request.post()
    ip = data.get("ip", "").strip()
    ssh_user = data.get("ssh_user", "root").strip() or "root"
    ssh_password = data.get("ssh_password", "").strip()
    ssh_key = data.get("ssh_key", "").strip()
    ssh_port = int(data.get("ssh_port", "22") or "22")
    is_relay = data.get("is_relay") == "on"
    relay_target = int(data.get("relay_target", "0") or "0")
    sni = data.get("sni", "www.google.com").strip() or "www.google.com"
    xray_port = int(data.get("xray_port", "443") or "443")

    if not ip or (not ssh_password and not ssh_key):
        servers = await get_all_servers()
        vpn_servers = [s for s in servers if not s["is_relay"] and s["xray_uuid"]]
        return aiohttp_jinja2.render_template("add_server.html", request, {
            "vpn_servers": vpn_servers,
            "error": "IP и пароль (или SSH ключ) обязательны",
            "success": ""
        })

    # Detect country
    geo = await detect_country(ip)
    cc = geo["country_code"]
    country = geo["country_name"]
    city = geo["city"]
    display_name = f"{country}" + (f", {city}" if city else "")

    if is_relay:
        server_id = await add_server(
            ip=ip, ssh_user=ssh_user, ssh_password=ssh_password, ssh_port=ssh_port,
            country_code=cc, country_name=country, city=city,
            display_name=f"WHITELIST {display_name}",
            is_relay=1, relay_target_id=relay_target if relay_target else None
        )
        if relay_target:
            from database import get_server as gs
            target = await gs(relay_target)
            if target:
                ok = await setup_relay(ip, ssh_user, ssh_password,
                                        target["ip"], target["xray_port"],
                                        xray_port, ssh_port,
                                        ssh_key=ssh_key)
                if not ok:
                    servers = await get_all_servers()
                    vpn_servers = [s for s in servers if not s["is_relay"] and s["xray_uuid"]]
                    return aiohttp_jinja2.render_template("add_server.html", request, {
                        "vpn_servers": vpn_servers,
                        "error": "Relay добавлен в БД, но настройка не удалась. Проверьте SSH.",
                        "success": ""
                    })
        raise web.HTTPFound("/admin/servers")
    else:
        server_id = await add_server(
            ip=ip, ssh_user=ssh_user, ssh_password=ssh_password, ssh_port=ssh_port,
            country_code=cc, country_name=country, city=city,
            display_name=display_name
        )
        # Auto-setup Xray
        result = await setup_server_full(ip, ssh_user, ssh_password, ssh_port, sni, xray_port, ssh_key=ssh_key)
        if "error" in result:
            servers = await get_all_servers()
            vpn_servers = [s for s in servers if not s["is_relay"] and s["xray_uuid"]]
            return aiohttp_jinja2.render_template("add_server.html", request, {
                "vpn_servers": vpn_servers,
                "error": f"Сервер добавлен, но Xray не установлен: {result['error']}",
                "success": ""
            })
        await update_server_xray(
            server_id,
            uuid_val=result["uuid"],
            private_key=result["private_key"],
            public_key=result["public_key"],
            short_id=result["short_id"],
            xray_port=result["port"],
            sni=result["sni"]
        )
        raise web.HTTPFound("/admin/servers")


async def delete_server_handler(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    server_id = int(request.match_info["id"])
    await delete_server(server_id)
    raise web.HTTPFound("/admin/servers")


async def toggle_server_handler(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    server_id = int(request.match_info["id"])
    active = int(request.match_info["active"])
    await toggle_server(server_id, bool(active))
    raise web.HTTPFound("/admin/servers")


async def reinstall_xray_handler(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    server_id = int(request.match_info["id"])
    s = await get_server(server_id)
    if not s:
        raise web.HTTPFound("/admin/servers")
    result = await setup_server_full(s["ip"], s["ssh_user"], s["ssh_password"], s["ssh_port"])
    if "error" not in result:
        await update_server_xray(
            server_id,
            uuid_val=result["uuid"],
            private_key=result["private_key"],
            public_key=result["public_key"],
            short_id=result["short_id"],
            xray_port=result["port"],
            sni=result["sni"]
        )
    raise web.HTTPFound("/admin/servers")


@aiohttp_jinja2.template("users.html")
async def users_page(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    query = request.rel_url.query.get("q", "").strip()
    if query:
        users = await search_users(query)
    else:
        users = await get_all_users()
    subs = await get_all_subscriptions()
    sub_map = {}
    for s in subs:
        if s["is_active"]:
            sub_map[s["user_id"]] = s
    await ensure_traffic_table()
    traffic_map = await get_all_traffic()
    user_list = []
    for u in users:
        uid = u["user_id"]
        t = traffic_map.get(uid, {"upload": 0, "download": 0})
        user_list.append({
            "user_id": uid,
            "username": u["username"],
            "first_name": u["first_name"],
            "balance": u["balance"],
            "created_at": u["created_at"],
            "has_sub": uid in sub_map,
            "sub_expires": sub_map[uid]["expires_at"][:10] if uid in sub_map else "",
            "upload": t["upload"],
            "download": t["download"],
        })
    return {"users": user_list, "query": query}


async def add_balance_handler(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    data = await request.post()
    user_id = int(data.get("user_id", 0))
    amount = float(data.get("amount", 0))
    if user_id and amount:
        await add_balance(user_id, amount)
    raise web.HTTPFound(f"/admin/users?q={user_id}")


async def export_users_csv(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    users = await get_all_users_with_payments()
    await ensure_traffic_table()
    traffic_map = await get_all_traffic()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Telegram ID", "Username", "First Name", "Balance",
                     "Total Paid", "Upload (MB)", "Download (MB)",
                     "Sub Token", "Sub Expires", "Created"])
    for u in users:
        uid = u["user_id"]
        t = traffic_map.get(uid, {"upload": 0, "download": 0})
        writer.writerow([
            uid,
            u["username"] or "",
            u["first_name"] or "",
            u["balance"],
            u["total_paid"],
            round(t["upload"] / 1048576, 2),
            round(t["download"] / 1048576, 2),
            u["sub_token"] or "",
            u["sub_expires"] or "",
            u["created_at"],
        ])

    resp = web.Response(
        text=output.getvalue(),
        content_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"}
    )
    return resp


@aiohttp_jinja2.template("settings.html")
async def settings_page(request):
    if not check_auth(request):
        raise web.HTTPFound("/admin/login")
    return {
        "price": config.PRICE_RUB,
        "channel": config.CHANNEL_ID,
        "cryptopay": bool(config.CRYPTOPAY_TOKEN),
        "lolz": bool(config.LOLZ_TOKEN),
    }


def create_web_app() -> web.Application:
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATES_DIR))

    # Routes
    app.router.add_get("/admin/login", login_page)
    app.router.add_post("/admin/login", login_post)
    app.router.add_get("/admin/logout", logout)
    app.router.add_get("/admin/dashboard", dashboard)
    app.router.add_get("/admin/", dashboard)
    app.router.add_get("/admin/servers", servers_page)
    app.router.add_get("/admin/servers/add", add_server_page)
    app.router.add_post("/admin/servers/add", add_server_post)
    app.router.add_get("/admin/servers/delete/{id}", delete_server_handler)
    app.router.add_get("/admin/servers/toggle/{id}/{active}", toggle_server_handler)
    app.router.add_get("/admin/servers/reinstall/{id}", reinstall_xray_handler)
    app.router.add_get("/admin/users", users_page)
    app.router.add_post("/admin/users/add_balance", add_balance_handler)
    app.router.add_get("/admin/users/export", export_users_csv)
    app.router.add_get("/admin/settings", settings_page)

    # Static files
    if os.path.exists(STATIC_DIR):
        app.router.add_static("/static", STATIC_DIR, name="static")

    return app
