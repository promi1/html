import asyncio
import csv
import io
import json
import logging
import os
from datetime import datetime, timedelta
from aiohttp import web
import aiohttp_jinja2
import jinja2
from config import config
from database import (get_all_servers, get_server, get_all_users, get_user_count,
                       get_active_sub_count, get_total_revenue, get_all_subscriptions,
                       add_server, delete_server, toggle_server, update_server_xray,
                       get_user, add_balance, search_users, get_user_total_payments,
                       get_all_users_with_payments, get_all_traffic, ensure_traffic_table,
                       get_users_registered_since, get_subs_started_since, get_revenue_since)
from services.country import detect_country
from services.xray_manager import (setup_server_full, setup_relay, check_server_alive,
                                    _setup_logs, cleanup_setup_logs)
from emoji import flag

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
HELP_DIR = os.path.join(PROJECT_ROOT, "help")
LEGAL_DIR = os.path.join(PROJECT_ROOT, "legal")

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

    now = datetime.utcnow()
    week_ago = (now - timedelta(days=7)).isoformat()
    two_weeks_ago = (now - timedelta(days=14)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()
    two_months_ago = (now - timedelta(days=60)).isoformat()

    users_this_week = await get_users_registered_since(week_ago)
    users_prev_week = await get_users_registered_since(two_weeks_ago) - users_this_week
    subs_this_week = await get_subs_started_since(week_ago)
    subs_prev_week = await get_subs_started_since(two_weeks_ago) - subs_this_week
    rev_this_month = await get_revenue_since(month_ago)
    rev_prev_month = await get_revenue_since(two_months_ago) - rev_this_month

    def calc_delta(current, previous):
        if previous > 0:
            return round((current - previous) / previous * 100)
        return 100 if current > 0 else 0

    return {
        "users": users,
        "subs": subs,
        "revenue": revenue,
        "servers": len(servers),
        "active_servers": len(active_servers),
        "price": config.PRICE_RUB,
        "delta_users": calc_delta(users_this_week, users_prev_week),
        "delta_subs": calc_delta(subs_this_week, subs_prev_week),
        "delta_revenue": calc_delta(rev_this_month, rev_prev_month),
        "users_this_week": users_this_week,
        "subs_this_week": subs_this_week,
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
    """Handle add server form — returns JSON for AJAX requests."""
    if not check_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)
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
        return web.json_response({"error": "IP и пароль (или SSH ключ) обязательны"})

    # Generate setup_id for log streaming
    import secrets as _sec
    setup_id = _sec.token_hex(8)

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
                    return web.json_response({"error": "Relay added but setup failed"})
        return web.json_response({"ok": True, "redirect": "/admin/servers"})
    else:
        server_id = await add_server(
            ip=ip, ssh_user=ssh_user, ssh_password=ssh_password, ssh_port=ssh_port,
            country_code=cc, country_name=country, city=city,
            display_name=display_name
        )

        async def run_setup():
            result = await setup_server_full(
                ip, ssh_user, ssh_password, ssh_port, sni, xray_port,
                ssh_key=ssh_key, setup_id=setup_id
            )
            # Store result in logs
            if setup_id not in _setup_logs:
                _setup_logs[setup_id] = []
            if "error" in result:
                import time
                _setup_logs[setup_id].append({
                    "ts": time.time(), "msg": f"FAILED: {result['error']}",
                    "level": "error", "done": True, "success": False
                })
            else:
                await update_server_xray(
                    server_id,
                    uuid_val=result["uuid"],
                    private_key=result["private_key"],
                    public_key=result["public_key"],
                    short_id=result["short_id"],
                    xray_port=result["port"],
                    sni=result["sni"]
                )
                import time
                _setup_logs[setup_id].append({
                    "ts": time.time(), "msg": "Server ready!",
                    "level": "success", "done": True, "success": True
                })

        # Run setup in background
        asyncio.ensure_future(run_setup())
        return web.json_response({"ok": True, "setup_id": setup_id, "country": display_name})


async def api_setup_logs(request):
    """SSE endpoint for streaming setup logs."""
    if not check_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    setup_id = request.match_info["setup_id"]
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
    await resp.prepare(request)
    seen = 0.0
    max_wait = 300  # 5 min max
    elapsed = 0
    try:
        while elapsed < max_wait:
            logs = _setup_logs.get(setup_id, [])
            new_logs = [e for e in logs if e["ts"] > seen]
            for entry in new_logs:
                seen = entry["ts"]
                payload = json.dumps(entry)
                await resp.write(f"data: {payload}\n\n".encode())
                if entry.get("done"):
                    cleanup_setup_logs(setup_id)
                    return resp
            await asyncio.sleep(0.5)
            elapsed += 0.5
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    return resp


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
        # Send Telegram notification to user
        try:
            bot = request.app.get("bot")
            if bot:
                user = await get_user(user_id)
                new_balance = user["balance"] if user else amount
                await bot.send_message(
                    user_id,
                    f"<b>Баланс пополнен!</b>\n\n"
                    f"Сумма: <b>+{amount:.0f} \u20bd</b>\n"
                    f"Текущий баланс: <b>{new_balance:.0f} \u20bd</b>",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.warning(f"Failed to send balance notification to {user_id}: {e}")
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


async def api_revenue(request):
    if not check_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    days = int(request.rel_url.query.get("days", "30"))
    labels = []
    values = []
    for i in range(days - 1, -1, -1):
        d = datetime.utcnow() - timedelta(days=i)
        labels.append(d.strftime("%d %b"))
        values.append(0)
    try:
        subs = await get_all_subscriptions()
        for s in subs:
            if s.get("started_at"):
                started = datetime.fromisoformat(s["started_at"])
                delta = (datetime.utcnow() - started).days
                if 0 <= delta < days:
                    idx = days - 1 - delta
                    values[idx] += config.PRICE_RUB
    except Exception:
        pass
    return web.json_response({"labels": labels, "values": values})


async def api_subs(request):
    if not check_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    days = int(request.rel_url.query.get("days", "30"))
    labels = []
    values = []
    for i in range(days - 1, -1, -1):
        d = datetime.utcnow() - timedelta(days=i)
        labels.append(d.strftime("%d %b"))
        values.append(0)
    try:
        subs = await get_all_subscriptions()
        active_count = len([s for s in subs if s.get("is_active")])
        for i in range(days):
            values[i] = active_count
    except Exception:
        pass
    return web.json_response({"labels": labels, "values": values})


async def api_check_server(request):
    if not check_auth(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    server_id = int(request.match_info["id"])
    s = await get_server(server_id)
    if not s:
        return web.json_response({"status": "error", "reason": "Server not found"})
    try:
        from services.xray_manager import run_ssh_command
        # Check SSH connectivity
        stdout, stderr, rc = await run_ssh_command(
            s["ip"], s["ssh_user"], s["ssh_password"],
            "echo ok && systemctl is-active xray 2>/dev/null || echo inactive",
            s["ssh_port"], timeout=15, ssh_key=(s["ssh_key"] if "ssh_key" in s.keys() else "")
        )
        if rc != 0 or "ok" not in stdout:
            reason = stderr.strip() if stderr.strip() else "SSH connection failed"
            return web.json_response({"status": "error", "reason": reason})
        lines = stdout.strip().split("\n")
        xray_status = lines[-1].strip() if len(lines) > 1 else "unknown"
        if xray_status == "active":
            return web.json_response({"status": "ok", "detail": "SSH OK, Xray running"})
        else:
            return web.json_response({"status": "warning", "detail": f"SSH OK, Xray: {xray_status}"})
    except asyncio.TimeoutError:
        return web.json_response({"status": "error", "reason": "SSH connection timed out"})
    except Exception as e:
        return web.json_response({"status": "error", "reason": str(e)})


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

    # API endpoints for dashboard charts
    app.router.add_get("/admin/api/revenue", api_revenue)
    app.router.add_get("/admin/api/subs", api_subs)
    app.router.add_get("/admin/api/servers/check/{id}", api_check_server)
    app.router.add_get("/admin/api/setup-logs/{setup_id}", api_setup_logs)

    # Static files
    if os.path.exists(STATIC_DIR):
        app.router.add_static("/static", STATIC_DIR, name="static")

    # Help / tutorial pages (static files)
    if os.path.exists(HELP_DIR):
        async def help_index(request):
            raise web.HTTPFound("/help/index.html")
        app.router.add_get("/help/", help_index)
        app.router.add_get("/help", help_index)
        app.router.add_static("/help", HELP_DIR, name="help")
    if os.path.exists(LEGAL_DIR):
        app.router.add_static("/legal", LEGAL_DIR, name="legal")

    return app
