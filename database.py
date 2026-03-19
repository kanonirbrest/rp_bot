import csv
import io
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

TURSO_URL = os.getenv("TURSO_URL", "").replace("libsql://", "https://")
TURSO_TOKEN = os.getenv("TURSO_TOKEN", "")

_settings_cache: dict[str, str | None] = {}


def _arg(value):
    if value is None:
        return {"type": "null"}
    elif isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    elif isinstance(value, float):
        return {"type": "float", "value": str(value)}
    else:
        return {"type": "text", "value": str(value)}


async def _execute(sql: str, args=None) -> dict:
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {"sql": sql, "args": [_arg(a) for a in (args or [])]},
            },
            {"type": "close"},
        ]
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{TURSO_URL}/v2/pipeline",
            headers={
                "Authorization": f"Bearer {TURSO_TOKEN}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    r.raise_for_status()
    return r.json()["results"][0]["response"]["result"]


def _rows(result: dict) -> list[dict]:
    cols = [c["name"] for c in result["cols"]]
    return [
        {cols[i]: (cell["value"] if cell["type"] != "null" else None) for i, cell in enumerate(row)}
        for row in result["rows"]
    ]


async def init_db():
    await _execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            phone TEXT,
            joined_at TEXT,
            giveaway_number INTEGER
        )
    """)
    await _execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    await _execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            project TEXT,
            rating INTEGER,
            email TEXT,
            text TEXT,
            created_at TEXT
        )
    """)
    await assign_missing_giveaway_numbers()


async def get_setting(key: str) -> str | None:
    if key in _settings_cache:
        return _settings_cache[key]
    result = await _execute("SELECT value FROM settings WHERE key = ?", [key])
    rows = _rows(result)
    value = rows[0]["value"] if rows else None
    _settings_cache[key] = value
    return value


async def set_setting(key: str, value: str):
    _settings_cache[key] = value
    await _execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [key, value],
    )


async def user_exists(user_id: int) -> bool:
    result = await _execute("SELECT user_id FROM users WHERE user_id = ?", [user_id])
    return len(_rows(result)) > 0


async def _next_giveaway_number() -> int:
    result = await _execute("SELECT MAX(giveaway_number) as max_num FROM users")
    rows = _rows(result)
    if rows and rows[0]["max_num"] is not None:
        return int(rows[0]["max_num"]) + 1
    return 1


async def assign_missing_giveaway_numbers():
    result = await _execute("SELECT id FROM users WHERE giveaway_number IS NULL ORDER BY id")
    for row in _rows(result):
        number = await _next_giveaway_number()
        await _execute("UPDATE users SET giveaway_number = ? WHERE id = ?", [number, int(row["id"])])


async def get_giveaway_number(user_id: int) -> int | None:
    result = await _execute("SELECT giveaway_number FROM users WHERE user_id = ?", [user_id])
    rows = _rows(result)
    val = rows[0]["giveaway_number"] if rows else None
    return int(val) if val is not None else None


async def add_user(user_id: int, username: str, first_name: str, last_name: str):
    if await user_exists(user_id):
        return
    number = await _next_giveaway_number()
    await _execute(
        "INSERT INTO users (user_id, username, first_name, last_name, joined_at, giveaway_number)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, username, first_name, last_name,
         datetime.now().isoformat(timespec="seconds"), number],
    )


async def get_all_user_ids() -> list[int]:
    result = await _execute("SELECT user_id FROM users")
    return [int(row["user_id"]) for row in _rows(result)]


async def save_phone(user_id: int, phone: str):
    await _execute("UPDATE users SET phone = ? WHERE user_id = ?", [phone, user_id])


async def get_stats() -> dict:
    count_result = await _execute("SELECT COUNT(*) as total FROM users")
    total = int(_rows(count_result)[0]["total"])

    recent_result = await _execute(
        "SELECT first_name, username, joined_at FROM users ORDER BY id DESC LIMIT 5"
    )
    recent = [
        (row["first_name"], row["username"], row["joined_at"])
        for row in _rows(recent_result)
    ]
    return {"total": total, "recent": recent}


async def save_review(user_id: int, project: str, rating: int, email: str | None, text: str):
    await _execute(
        "INSERT INTO reviews (user_id, project, rating, email, text, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        [user_id, project, rating, email, text, datetime.now().isoformat(timespec="seconds")],
    )


async def export_csv() -> str:
    result = await _execute(
        "SELECT user_id, username, first_name, last_name, phone, joined_at FROM users ORDER BY id"
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "phone", "joined_at"])
    for row in _rows(result):
        writer.writerow([row["user_id"], row["username"], row["first_name"],
                         row["last_name"], row["phone"], row["joined_at"]])
    return output.getvalue()
