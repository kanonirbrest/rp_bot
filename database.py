import csv
import io
import os
from contextlib import contextmanager
from datetime import datetime

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")


@contextmanager
def _conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id               SERIAL PRIMARY KEY,
                    user_id          BIGINT UNIQUE NOT NULL,
                    username         TEXT,
                    first_name       TEXT,
                    last_name        TEXT,
                    phone            TEXT,
                    joined_at        TEXT NOT NULL,
                    giveaway_number  INTEGER UNIQUE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
    assign_missing_giveaway_numbers()


def get_setting(key: str) -> str | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None


def set_setting(key: str, value: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, value),
            )


def user_exists(user_id: int) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone() is not None


def _next_giveaway_number(cur) -> int:
    cur.execute("SELECT MAX(giveaway_number) FROM users")
    row = cur.fetchone()
    return (row[0] or 0) + 1


def assign_missing_giveaway_numbers():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE giveaway_number IS NULL ORDER BY id"
            )
            rows = cur.fetchall()
            for (row_id,) in rows:
                number = _next_giveaway_number(cur)
                cur.execute(
                    "UPDATE users SET giveaway_number = %s WHERE id = %s",
                    (number, row_id),
                )


def get_giveaway_number(user_id: int) -> int | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT giveaway_number FROM users WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
            return row[0] if row else None


def add_user(user_id: int, username: str, first_name: str, last_name: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            number = _next_giveaway_number(cur)
            cur.execute(
                """
                INSERT INTO users
                    (user_id, username, first_name, last_name, joined_at, giveaway_number)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id, username, first_name, last_name,
                 datetime.now().isoformat(timespec="seconds"), number),
            )


def get_all_user_ids() -> list[int]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            return [row[0] for row in cur.fetchall()]


def save_phone(user_id: int, phone: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET phone = %s WHERE user_id = %s", (phone, user_id)
            )


def get_stats() -> dict:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT first_name, username, joined_at FROM users ORDER BY id DESC LIMIT 5"
            )
            recent = cur.fetchall()
            return {"total": total, "recent": recent}


def export_csv() -> str:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, first_name, last_name, phone, joined_at FROM users ORDER BY id"
            )
            rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "phone", "joined_at"])
    writer.writerows(rows)
    return output.getvalue()
