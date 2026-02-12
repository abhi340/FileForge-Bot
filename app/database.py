import libsql_experimental as libsql
from typing import Optional
from datetime import date

from app.config import logger

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS whitelist (
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        is_suspended INTEGER DEFAULT 0,
        daily_limit INTEGER DEFAULT 50,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS usage_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        file_type TEXT NOT NULL,
        tool_used TEXT NOT NULL,
        file_size INTEGER DEFAULT 0,
        status TEXT DEFAULT 'success',
        error_message TEXT DEFAULT '',
        processing_time_ms INTEGER DEFAULT 0,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS system_stats (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]


class Database:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.conn = None

    async def connect(self):
        self.conn = libsql.connect("local.db", sync_url=self.url, auth_token=self.token)
        self.conn.sync()
        for stmt in SCHEMA:
            self.conn.execute(stmt)
        self.conn.commit()
        self.conn.sync()
        logger.info("Database ready (Turso)")

    def fetch_one(self, query, params=()):
        cursor = self.conn.execute(query, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip(columns, row))

    def fetch_all(self, query, params=()):
        cursor = self.conn.execute(query, params)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]

    def execute(self, query, params=()):
        self.conn.execute(query, params)
        self.conn.commit()
        try:
            self.conn.sync()
        except Exception as e:
            logger.warning(f"Sync failed (non-critical): {e}")

    async def disconnect(self):
        try:
            if self.conn:
                self.conn.sync()
        except Exception:
            pass
        logger.info("Database disconnected")


class WhitelistRepo:
    def __init__(self, db):
        self.db = db

    async def add_user(self, user_id, username=""):
        if await self.get_user(user_id):
            return False
        self.db.execute(
            "INSERT INTO whitelist (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        logger.info(f"User added: {user_id}")
        return True

    async def remove_user(self, user_id):
        if not await self.get_user(user_id):
            return False
        self.db.execute("DELETE FROM whitelist WHERE user_id=?", (user_id,))
        logger.info(f"User removed: {user_id}")
        return True

    async def get_user(self, user_id):
        return self.db.fetch_one("SELECT * FROM whitelist WHERE user_id=?", (user_id,))

    async def is_whitelisted(self, user_id):
        user = await self.get_user(user_id)
        return user is not None and bool(user["is_active"])

    async def is_suspended(self, user_id):
        user = await self.get_user(user_id)
        return user is not None and bool(user["is_suspended"])

    async def suspend_user(self, user_id):
        if not await self.get_user(user_id):
            return False
        self.db.execute(
            "UPDATE whitelist SET is_suspended=1, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (user_id,),
        )
        return True

    async def unsuspend_user(self, user_id):
        if not await self.get_user(user_id):
            return False
        self.db.execute(
            "UPDATE whitelist SET is_suspended=0, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (user_id,),
        )
        return True

    async def set_daily_limit(self, user_id, limit):
        if not await self.get_user(user_id):
            return False
        self.db.execute(
            "UPDATE whitelist SET daily_limit=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (limit, user_id),
        )
        return True

    async def list_users(self):
        return self.db.fetch_all("SELECT * FROM whitelist ORDER BY created_at DESC")

    async def get_active_user_ids(self):
        rows = self.db.fetch_all(
            "SELECT user_id FROM whitelist WHERE is_active=1 AND is_suspended=0"
        )
        return [r["user_id"] for r in rows]

    async def get_daily_usage(self, user_id):
        today = date.today().isoformat()
        r = self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=? AND DATE(timestamp)=?",
            (user_id, today),
        )
        return r["c"] if r else 0

    async def check_daily_limit(self, user_id):
        user = await self.get_user(user_id)
        if not user:
            return False
        usage = await self.get_daily_usage(user_id)
        return usage < user["daily_limit"]


class UsageRepo:
    def __init__(self, db):
        self.db = db

    async def log(self, user_id, file_type, tool_used,
                  file_size=0, status="success",
                  error_message="", processing_time_ms=0):
        self.db.execute(
            """INSERT INTO usage_logs
            (user_id, file_type, tool_used, file_size, status, error_message, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, file_type, tool_used, file_size, status, error_message, processing_time_ms),
        )

    async def total_processed(self):
        r = self.db.fetch_one("SELECT COUNT(*) as c FROM usage_logs")
        return r["c"] if r else 0

    async def today_processed(self):
        today = date.today().isoformat()
        r = self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE DATE(timestamp)=?", (today,)
        )
        return r["c"] if r else 0

    async def success_failure(self):
        rows = self.db.fetch_all(
            "SELECT status, COUNT(*) as c FROM usage_logs GROUP BY status"
        )
        result = {"success": 0, "failure": 0}
        for row in rows:
            if row["status"] == "success":
                result["success"] = row["c"]
            else:
                result["failure"] += row["c"]
        return result

    async def file_type_dist(self):
        return self.db.fetch_all(
            "SELECT file_type, COUNT(*) as c FROM usage_logs GROUP BY file_type ORDER BY c DESC"
        )

    async def top_users(self, limit=5):
        return self.db.fetch_all(
            "SELECT user_id, COUNT(*) as c FROM usage_logs GROUP BY user_id ORDER BY c DESC LIMIT ?",
            (limit,),
        )

    async def avg_time(self):
        r = self.db.fetch_one(
            "SELECT AVG(processing_time_ms) as a FROM usage_logs WHERE status='success'"
        )
        return round(r["a"] or 0, 2) if r and r["a"] else 0.0

    async def error_count(self):
        r = self.db.fetch_one("SELECT COUNT(*) as c FROM usage_logs WHERE status!='success'")
        return r["c"] if r else 0

    async def active_today(self):
        today = date.today().isoformat()
        r = self.db.fetch_one(
            "SELECT COUNT(DISTINCT user_id) as c FROM usage_logs WHERE DATE(timestamp)=?",
            (today,),
        )
        return r["c"] if r else 0

    async def user_total(self, user_id):
        r = self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=?", (user_id,)
        )
        return r["c"] if r else 0

    async def user_today(self, user_id):
        today = date.today().isoformat()
        r = self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=? AND DATE(timestamp)=?",
            (user_id, today),
        )
        return r["c"] if r else 0

    async def user_fail_rate(self, user_id):
        total = await self.user_total(user_id)
        if total == 0:
            return 0.0
        r = self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=? AND status!='success'",
            (user_id,),
        )
        return round(((r["c"] if r else 0) / total) * 100, 2)

    async def user_fav_type(self, user_id):
        r = self.db.fetch_one(
            "SELECT file_type FROM usage_logs WHERE user_id=? GROUP BY file_type ORDER BY COUNT(*) DESC LIMIT 1",
            (user_id,),
        )
        return r["file_type"] if r else "N/A"


class SystemRepo:
    def __init__(self, db):
        self.db = db

    async def set_stat(self, key, value):
        self.db.execute(
            """INSERT INTO system_stats (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=?, updated_at=CURRENT_TIMESTAMP""",
            (key, value, value),
        )

    async def get_stat(self, key, default=""):
        r = self.db.fetch_one("SELECT value FROM system_stats WHERE key=?", (key,))
        return r["value"] if r else default
