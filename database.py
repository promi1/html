import aiosqlite
import logging
from datetime import datetime
from config import config

logger = logging.getLogger(__name__)
DB_PATH = config.DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                ssh_user TEXT DEFAULT 'root',
                ssh_password TEXT,
                ssh_key TEXT DEFAULT '',
                ssh_port INTEGER DEFAULT 22,
                country_code TEXT DEFAULT '',
                country_name TEXT DEFAULT '',
                city TEXT DEFAULT '',
                xray_port INTEGER DEFAULT 443,
                xray_uuid TEXT,
                xray_private_key TEXT,
                xray_public_key TEXT,
                xray_short_id TEXT,
                xray_sni TEXT DEFAULT 'www.google.com',
                is_active INTEGER DEFAULT 1,
                is_relay INTEGER DEFAULT 0,
                relay_target_id INTEGER,
                display_name TEXT DEFAULT '',
                speed TEXT DEFAULT '10 Gbps',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(relay_target_id) REFERENCES servers(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                sub_token TEXT UNIQUE NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                method TEXT NOT NULL,
                payment_id TEXT UNIQUE,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()
    logger.info("Database initialized")


# ─── Users ───────────────────────────────────────────────────────────────

async def get_or_create_user(user_id: int, username: str = None, first_name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name)
            )
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
        return row


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone()


async def add_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()


async def deduct_balance(user_id: int, amount: float) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        return True


async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users ORDER BY created_at DESC") as cur:
            return await cur.fetchall()


async def get_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0]


async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        await db.commit()


# ─── Servers ─────────────────────────────────────────────────────────────

async def add_server(ip: str, ssh_user: str, ssh_password: str, ssh_port: int = 22,
                     country_code: str = "", country_name: str = "", city: str = "",
                     display_name: str = "", speed: str = "10 Gbps",
                     is_relay: int = 0, relay_target_id: int = None,
                     ssh_key: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO servers (ip, ssh_user, ssh_password, ssh_key, ssh_port,
                                 country_code, country_name, city, display_name, speed,
                                 is_relay, relay_target_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ip, ssh_user, ssh_password, ssh_key, ssh_port,
              country_code, country_name, city, display_name, speed,
              is_relay, relay_target_id))
        await db.commit()
        return cur.lastrowid


async def update_server_xray(server_id: int, uuid_val: str, private_key: str,
                              public_key: str, short_id: str, xray_port: int = 443,
                              sni: str = "www.google.com"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE servers SET xray_uuid=?, xray_private_key=?, xray_public_key=?,
                               xray_short_id=?, xray_port=?, xray_sni=?
            WHERE id=?
        """, (uuid_val, private_key, public_key, short_id, xray_port, sni, server_id))
        await db.commit()


async def get_server(server_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM servers WHERE id = ?", (server_id,)) as cur:
            return await cur.fetchone()


async def get_all_servers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM servers ORDER BY id") as cur:
            return await cur.fetchall()


async def get_active_servers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM servers WHERE is_active = 1 AND xray_uuid IS NOT NULL ORDER BY id"
        ) as cur:
            return await cur.fetchall()


async def get_active_vpn_servers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM servers WHERE is_active = 1 AND is_relay = 0 AND xray_uuid IS NOT NULL ORDER BY id"
        ) as cur:
            return await cur.fetchall()


async def get_relay_servers():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM servers WHERE is_active = 1 AND is_relay = 1 ORDER BY id"
        ) as cur:
            return await cur.fetchall()


async def delete_server(server_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
        await db.commit()


async def toggle_server(server_id: int, active: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE servers SET is_active = ? WHERE id = ?", (1 if active else 0, server_id))
        await db.commit()


# ─── Subscriptions ───────────────────────────────────────────────────────

async def create_subscription(user_id: int, started_at: str, expires_at: str, sub_token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO subscriptions (user_id, started_at, expires_at, sub_token)
            VALUES (?, ?, ?, ?)
        """, (user_id, started_at, expires_at, sub_token))
        await db.commit()


async def get_active_subscription(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM subscriptions WHERE user_id = ? AND is_active = 1
            ORDER BY expires_at DESC LIMIT 1
        """, (user_id,)) as cur:
            return await cur.fetchone()


async def get_subscription_by_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE sub_token = ? AND is_active = 1", (token,)
        ) as cur:
            return await cur.fetchone()


async def get_expiring_subscriptions():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = datetime.utcnow().isoformat()
        async with db.execute("""
            SELECT * FROM subscriptions WHERE is_active = 1 AND expires_at <= ?
        """, (now,)) as cur:
            return await cur.fetchall()


async def deactivate_subscription(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET is_active = 0 WHERE id = ?", (sub_id,))
        await db.commit()


async def renew_subscription(sub_id: int, new_expires_at: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE subscriptions SET expires_at = ?, is_active = 1 WHERE id = ?
        """, (new_expires_at, sub_id))
        await db.commit()


async def get_all_subscriptions():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, u.username, u.first_name FROM subscriptions s
            JOIN users u ON s.user_id = u.user_id
            ORDER BY s.expires_at DESC
        """) as cur:
            return await cur.fetchall()


async def get_active_sub_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM subscriptions WHERE is_active = 1") as cur:
            row = await cur.fetchone()
            return row[0]


# ─── Payments ────────────────────────────────────────────────────────────

async def create_payment(user_id: int, amount: float, currency: str, method: str, payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO payments (user_id, amount, currency, method, payment_id)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, amount, currency, method, payment_id))
        await db.commit()


async def get_payment(payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)) as cur:
            return await cur.fetchone()


async def update_payment_status(payment_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE payments SET status = ? WHERE payment_id = ?", (status, payment_id))
        await db.commit()


async def get_total_revenue():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid'") as cur:
            row = await cur.fetchone()
            return row[0]


# ─── Users (extended) ────────────────────────────────────────────────────

async def search_users(query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        like = f"%{query}%"
        async with db.execute("""
            SELECT * FROM users
            WHERE username LIKE ? OR first_name LIKE ? OR CAST(user_id AS TEXT) LIKE ?
            ORDER BY created_at DESC
        """, (like, like, like)) as cur:
            return await cur.fetchall()


async def get_user_total_payments(user_id: int) -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE user_id = ? AND status = 'paid'",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def get_all_users_with_payments():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.*,
                   COALESCE(p.total_paid, 0) as total_paid,
                   s.sub_token, s.expires_at as sub_expires
            FROM users u
            LEFT JOIN (SELECT user_id, SUM(amount) as total_paid FROM payments WHERE status='paid' GROUP BY user_id) p
                ON u.user_id = p.user_id
            LEFT JOIN (SELECT user_id, sub_token, expires_at FROM subscriptions WHERE is_active=1) s
                ON u.user_id = s.user_id
            ORDER BY u.created_at DESC
        """) as cur:
            return await cur.fetchall()


# ─── Traffic ─────────────────────────────────────────────────────────────

async def ensure_traffic_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS traffic (
                user_id INTEGER NOT NULL,
                upload INTEGER DEFAULT 0,
                download INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def update_traffic(user_id: int, upload: int, download: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO traffic (user_id, upload, download, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                upload = upload + excluded.upload,
                download = download + excluded.download,
                updated_at = CURRENT_TIMESTAMP
        """, (user_id, upload, download))
        await db.commit()


async def get_traffic(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM traffic WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)
            return {"user_id": user_id, "upload": 0, "download": 0}


async def get_all_traffic():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM traffic") as cur:
            rows = await cur.fetchall()
            return {r["user_id"]: dict(r) for r in rows}


# ─── KPI deltas ─────────────────────────────────────────────────────────

async def get_users_registered_since(since_iso: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (since_iso,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def get_subs_started_since(since_iso: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE started_at >= ?", (since_iso,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def get_revenue_since(since_iso: str) -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'paid' AND created_at >= ?",
            (since_iso,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


# ─── Settings ────────────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        await db.commit()
