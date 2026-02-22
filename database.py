import csv
import io
import os
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_client: Client | None = None


def _db() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def init_db():
    assign_missing_giveaway_numbers()


def get_setting(key: str) -> str | None:
    result = _db().table("settings").select("value").eq("key", key).execute()
    return result.data[0]["value"] if result.data else None


def set_setting(key: str, value: str):
    _db().table("settings").upsert({"key": key, "value": value}).execute()


def user_exists(user_id: int) -> bool:
    result = _db().table("users").select("user_id").eq("user_id", user_id).execute()
    return len(result.data) > 0


def _next_giveaway_number() -> int:
    result = (
        _db()
        .table("users")
        .select("giveaway_number")
        .order("giveaway_number", desc=True)
        .limit(1)
        .execute()
    )
    if result.data and result.data[0]["giveaway_number"] is not None:
        return result.data[0]["giveaway_number"] + 1
    return 1


def assign_missing_giveaway_numbers():
    result = (
        _db()
        .table("users")
        .select("id")
        .is_("giveaway_number", "null")
        .order("id")
        .execute()
    )
    for row in result.data:
        number = _next_giveaway_number()
        _db().table("users").update({"giveaway_number": number}).eq("id", row["id"]).execute()


def get_giveaway_number(user_id: int) -> int | None:
    result = _db().table("users").select("giveaway_number").eq("user_id", user_id).execute()
    return result.data[0]["giveaway_number"] if result.data else None


def add_user(user_id: int, username: str, first_name: str, last_name: str):
    if user_exists(user_id):
        return
    number = _next_giveaway_number()
    _db().table("users").insert({
        "user_id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "joined_at": datetime.now().isoformat(timespec="seconds"),
        "giveaway_number": number,
    }).execute()


def get_all_user_ids() -> list[int]:
    result = _db().table("users").select("user_id").execute()
    return [row["user_id"] for row in result.data]


def save_phone(user_id: int, phone: str):
    _db().table("users").update({"phone": phone}).eq("user_id", user_id).execute()


def get_stats() -> dict:
    total_result = _db().table("users").select("*", count="exact").execute()
    total = total_result.count or 0
    recent_result = (
        _db()
        .table("users")
        .select("first_name,username,joined_at")
        .order("id", desc=True)
        .limit(5)
        .execute()
    )
    recent = [
        (r["first_name"], r["username"], r["joined_at"])
        for r in recent_result.data
    ]
    return {"total": total, "recent": recent}


def export_csv() -> str:
    result = (
        _db()
        .table("users")
        .select("user_id,username,first_name,last_name,phone,joined_at")
        .order("id")
        .execute()
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "phone", "joined_at"])
    for row in result.data:
        writer.writerow([
            row["user_id"], row["username"], row["first_name"],
            row["last_name"], row["phone"], row["joined_at"],
        ])
    return output.getvalue()
