import csv
import io
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")


def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _headers(prefer: str = "") -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def init_db():
    assign_missing_giveaway_numbers()


def get_setting(key: str) -> str | None:
    r = httpx.get(_url("settings"), headers=_headers(),
                  params={"key": f"eq.{key}", "select": "value"})
    data = r.json()
    return data[0]["value"] if data else None


def set_setting(key: str, value: str):
    httpx.post(_url("settings"),
               headers=_headers("resolution=merge-duplicates"),
               json={"key": key, "value": value})


def user_exists(user_id: int) -> bool:
    r = httpx.get(_url("users"), headers=_headers(),
                  params={"user_id": f"eq.{user_id}", "select": "user_id"})
    return len(r.json()) > 0


def _next_giveaway_number() -> int:
    r = httpx.get(_url("users"), headers=_headers(),
                  params={"select": "giveaway_number",
                          "order": "giveaway_number.desc", "limit": "1"})
    data = r.json()
    if data and data[0]["giveaway_number"] is not None:
        return data[0]["giveaway_number"] + 1
    return 1


def assign_missing_giveaway_numbers():
    r = httpx.get(_url("users"), headers=_headers(),
                  params={"select": "id", "giveaway_number": "is.null", "order": "id"})
    for row in r.json():
        number = _next_giveaway_number()
        httpx.patch(_url("users"), headers=_headers("return=minimal"),
                    params={"id": f"eq.{row['id']}"},
                    json={"giveaway_number": number})


def get_giveaway_number(user_id: int) -> int | None:
    r = httpx.get(_url("users"), headers=_headers(),
                  params={"user_id": f"eq.{user_id}", "select": "giveaway_number"})
    data = r.json()
    return data[0]["giveaway_number"] if data else None


def add_user(user_id: int, username: str, first_name: str, last_name: str):
    if user_exists(user_id):
        return
    number = _next_giveaway_number()
    httpx.post(_url("users"), headers=_headers("return=minimal"),
               json={"user_id": user_id, "username": username,
                     "first_name": first_name, "last_name": last_name,
                     "joined_at": datetime.now().isoformat(timespec="seconds"),
                     "giveaway_number": number})


def get_all_user_ids() -> list[int]:
    r = httpx.get(_url("users"), headers=_headers(), params={"select": "user_id"})
    return [row["user_id"] for row in r.json()]


def save_phone(user_id: int, phone: str):
    httpx.patch(_url("users"), headers=_headers("return=minimal"),
                params={"user_id": f"eq.{user_id}"},
                json={"phone": phone})


def get_stats() -> dict:
    r = httpx.get(_url("users"),
                  headers={**_headers(), "Prefer": "count=exact"},
                  params={"select": "*"})
    content_range = r.headers.get("content-range", "0/0")
    total = int(content_range.split("/")[-1]) if "/" in content_range else 0

    r2 = httpx.get(_url("users"), headers=_headers(),
                   params={"select": "first_name,username,joined_at",
                           "order": "id.desc", "limit": "5"})
    recent = [(row["first_name"], row["username"], row["joined_at"])
              for row in r2.json()]
    return {"total": total, "recent": recent}


def export_csv() -> str:
    r = httpx.get(_url("users"), headers=_headers(),
                  params={"select": "user_id,username,first_name,last_name,phone,joined_at",
                          "order": "id"})
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "phone", "joined_at"])
    for row in r.json():
        writer.writerow([row["user_id"], row["username"], row["first_name"],
                         row["last_name"], row["phone"], row["joined_at"]])
    return output.getvalue()
