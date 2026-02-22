import sqlite3
from datetime import datetime

DB_PATH = "users.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER UNIQUE NOT NULL,
                username         TEXT,
                first_name       TEXT,
                last_name        TEXT,
                phone            TEXT,
                joined_at        TEXT NOT NULL,
                giveaway_number  INTEGER UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # миграция для уже существующих баз без колонки giveaway_number
        existing = [row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "giveaway_number" not in existing:
            conn.execute("ALTER TABLE users ADD COLUMN giveaway_number INTEGER UNIQUE")
        conn.commit()
    assign_missing_giveaway_numbers()


def get_setting(key: str) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def user_exists(user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None


def _next_giveaway_number(conn) -> int:
    row = conn.execute("SELECT MAX(giveaway_number) FROM users").fetchone()
    return (row[0] or 0) + 1


def assign_missing_giveaway_numbers():
    with sqlite3.connect(DB_PATH) as conn:
        users = conn.execute(
            "SELECT id FROM users WHERE giveaway_number IS NULL ORDER BY id"
        ).fetchall()
        for (row_id,) in users:
            number = _next_giveaway_number(conn)
            conn.execute(
                "UPDATE users SET giveaway_number = ? WHERE id = ?", (number, row_id)
            )
        conn.commit()


def get_giveaway_number(user_id: int) -> int | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT giveaway_number FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else None


def add_user(user_id: int, username: str, first_name: str, last_name: str):
    with sqlite3.connect(DB_PATH) as conn:
        number = _next_giveaway_number(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO users
                (user_id, username, first_name, last_name, joined_at, giveaway_number)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, username, first_name, last_name,
             datetime.now().isoformat(timespec="seconds"), number),
        )
        conn.commit()


def get_all_user_ids() -> list[int]:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT user_id FROM users").fetchall()
        return [row[0] for row in rows]


def save_phone(user_id: int, phone: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id)
        )
        conn.commit()


def get_stats() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        recent = conn.execute(
            "SELECT first_name, username, joined_at FROM users ORDER BY id DESC LIMIT 5"
        ).fetchall()
        return {"total": total, "recent": recent}


def export_csv() -> str:
    import csv
    import io

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT user_id, username, first_name, last_name, phone, joined_at FROM users ORDER BY id"
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "phone", "joined_at"])
    writer.writerows(rows)
    return output.getvalue()
