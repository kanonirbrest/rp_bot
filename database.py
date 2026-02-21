import sqlite3
from datetime import datetime

DB_PATH = "users.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER UNIQUE NOT NULL,
                username    TEXT,
                first_name  TEXT,
                last_name   TEXT,
                phone       TEXT,
                joined_at   TEXT NOT NULL
            )
        """)
        conn.commit()


def user_exists(user_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None


def add_user(user_id: int, username: str, first_name: str, last_name: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, username, first_name, last_name, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


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
