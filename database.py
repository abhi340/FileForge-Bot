"""
Database — connection, schema, and all repositories.
"""

import aiosqlite
from pathlib import Path
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
    "CREATE INDEX IF NOT EXISTS idx_logs_user ON usage_logs(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_logs_time ON usage_logs(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_logs_status ON usage_logs(status)",
]


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        for stmt in SCHEMA:
            await self._conn.execute(stmt)
        await self._conn.commit()
        logger.info(f"Database ready: {self.db_path}")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        cursor = await self.conn.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        cursor = await self.conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def execute(self, query: str, params: tuple = ()) -> None:
        await self.conn.execute(query, params)
        await self.conn.commit()

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("Database disconnected")


class WhitelistRepo:
    def __init__(self, db: Database):
        self.db = db

    async def add_user(self, user_id: int, username: str = "") -> bool:
        if await self.get_user(user_id):
            return False
        await self.db.execute(
            "INSERT INTO whitelist (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        logger.info(f"User added: {user_id}")
        return True

    async def remove_user(self, user_id: int) -> bool:
        if not await self.get_user(user_id):
            return False
        await self.db.execute("DELETE FROM whitelist WHERE user_id=?", (user_id,))
        logger.info(f"User removed: {user_id}")
        return True

    async def get_user(self, user_id: int) -> Optional[dict]:
        return await self.db.fetch_one("SELECT * FROM whitelist WHERE user_id=?", (user_id,))

    async def is_whitelisted(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return user is not None and bool(user["is_active"])

    async def is_suspended(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        return user is not None and bool(user["is_suspended"])

    async def suspend_user(self, user_id: int) -> bool:
        if not await self.get_user(user_id):
            return False
        await self.db.execute(
            "UPDATE whitelist SET is_suspended=1, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (user_id,),
        )
        return True

    async def unsuspend_user(self, user_id: int) -> bool:
        if not await self.get_user(user_id):
            return False
        await self.db.execute(
            "UPDATE whitelist SET is_suspended=0, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (user_id,),
        )
        return True

    async def set_daily_limit(self, user_id: int, limit: int) -> bool:
        if not await self.get_user(user_id):
            return False
        await self.db.execute(
            "UPDATE whitelist SET daily_limit=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (limit, user_id),
        )
        return True

    async def list_users(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM whitelist ORDER BY created_at DESC")

    async def get_active_user_ids(self) -> list[int]:
        rows = await self.db.fetch_all(
            "SELECT user_id FROM whitelist WHERE is_active=1 AND is_suspended=0"
        )
        return [r["user_id"] for r in rows]

    async def get_daily_usage(self, user_id: int) -> int:
        today = date.today().isoformat()
        r = await self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=? AND DATE(timestamp)=?",
            (user_id, today),
        )
        return r["c"] if r else 0

    async def check_daily_limit(self, user_id: int) -> bool:
        user = await self.get_user(user_id)
        if not user:
            return False
        usage = await self.get_daily_usage(user_id)
        return usage < user["daily_limit"]


class UsageRepo:
    def __init__(self, db: Database):
        self.db = db

    async def log(self, user_id: int, file_type: str, tool_used: str,
                  file_size: int = 0, status: str = "success",
                  error_message: str = "", processing_time_ms: int = 0) -> None:
        await self.db.execute(
            """INSERT INTO usage_logs
            (user_id, file_type, tool_used, file_size, status, error_message, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, file_type, tool_used, file_size, status, error_message, processing_time_ms),
        )

    async def total_processed(self) -> int:
        r = await self.db.fetch_one("SELECT COUNT(*) as c FROM usage_logs")
        return r["c"] if r else 0

    async def today_processed(self) -> int:
        today = date.today().isoformat()
        r = await self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE DATE(timestamp)=?", (today,)
        )
        return r["c"] if r else 0

    async def success_failure(self) -> dict:
        rows = await self.db.fetch_all(
            "SELECT status, COUNT(*) as c FROM usage_logs GROUP BY status"
        )
        result = {"success": 0, "failure": 0}
        for row in rows:
            if row["status"] == "success":
                result["success"] = row["c"]
            else:
                result["failure"] += row["c"]
        return result

    async def file_type_dist(self) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT file_type, COUNT(*) as c FROM usage_logs GROUP BY file_type ORDER BY c DESC"
        )

    async def top_users(self, limit: int = 5) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT user_id, COUNT(*) as c FROM usage_logs GROUP BY user_id ORDER BY c DESC LIMIT ?",
            (limit,),
        )

    async def avg_time(self) -> float:
        r = await self.db.fetch_one(
            "SELECT AVG(processing_time_ms) as a FROM usage_logs WHERE status='success'"
        )
        return round(r["a"] or 0, 2) if r else 0.0

    async def error_count(self) -> int:
        r = await self.db.fetch_one("SELECT COUNT(*) as c FROM usage_logs WHERE status!='success'")
        return r["c"] if r else 0

    async def active_today(self) -> int:
        today = date.today().isoformat()
        r = await self.db.fetch_one(
            "SELECT COUNT(DISTINCT user_id) as c FROM usage_logs WHERE DATE(timestamp)=?",
            (today,),
        )
        return r["c"] if r else 0

    async def user_total(self, user_id: int) -> int:
        r = await self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=?", (user_id,)
        )
        return r["c"] if r else 0

    async def user_today(self, user_id: int) -> int:
        today = date.today().isoformat()
        r = await self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=? AND DATE(timestamp)=?",
            (user_id, today),
        )
        return r["c"] if r else 0

    async def user_fail_rate(self, user_id: int) -> float:
        total = await self.user_total(user_id)
        if total == 0:
            return 0.0
        r = await self.db.fetch_one(
            "SELECT COUNT(*) as c FROM usage_logs WHERE user_id=? AND status!='success'",
            (user_id,),
        )
        return round(((r["c"] if r else 0) / total) * 100, 2)

    async def user_fav_type(self, user_id: int) -> str:
        r = await self.db.fetch_one(
            "SELECT file_type FROM usage_logs WHERE user_id=? GROUP BY file_type ORDER BY COUNT(*) DESC LIMIT 1",
            (user_id,),
        )
        return r["file_type"] if r else "N/A"


class SystemRepo:
    def __init__(self, db: Database):
        self.db = db

    async def set_stat(self, key: str, value: str) -> None:
        await self.db.execute(
            """INSERT INTO system_stats (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=?, updated_at=CURRENT_TIMESTAMP""",
            (key, value, value),
        )

    async def get_stat(self, key: str, default: str = "") -> str:
        r = await self.db.fetch_one("SELECT value FROM system_stats WHERE key=?", (key,))
        return r["value"] if r else default
