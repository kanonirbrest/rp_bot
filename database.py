import csv
import io
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Кеш настроек в памяти
_settings_cache: dict[str, str | None] = {}


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


async def init_db():
    await assign_missing_giveaway_numbers()


async def get_setting(key: str) -> str | None:
    if key in _settings_cache:
        return _settings_cache[key]
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(_url("settings"), headers=_headers(),
                             params={"key": f"eq.{key}", "select": "value"})
    data = r.json()
    value = data[0]["value"] if data else None
    _settings_cache[key] = value
    return value


async def set_setting(key: str, value: str):
    _settings_cache[key] = value
    async with httpx.AsyncClient() as client:
        await client.post(_url("settings"),
                          headers=_headers("resolution=merge-duplicates"),
                          json={"key": key, "value": value})


async def user_exists(user_id: int) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.get(_url("users"), headers=_headers(),
                             params={"user_id": f"eq.{user_id}", "select": "user_id"})
    return len(r.json()) > 0


async def _next_giveaway_number(client: httpx.AsyncClient) -> int:
    r = await client.get(_url("users"), headers=_headers(),
                         params={"select": "giveaway_number",
                                 "order": "giveaway_number.desc", "limit": "1"})
    data = r.json()
    if data and data[0]["giveaway_number"] is not None:
        return data[0]["giveaway_number"] + 1
    return 1


async def assign_missing_giveaway_numbers():
    async with httpx.AsyncClient() as client:
        r = await client.get(_url("users"), headers=_headers(),
                             params={"select": "id", "giveaway_number": "is.null", "order": "id"})
        for row in r.json():
            number = await _next_giveaway_number(client)
            await client.patch(_url("users"), headers=_headers("return=minimal"),
                               params={"id": f"eq.{row['id']}"},
                               json={"giveaway_number": number})


async def get_giveaway_number(user_id: int) -> int | None:
    async with httpx.AsyncClient() as client:
        r = await client.get(_url("users"), headers=_headers(),
                             params={"user_id": f"eq.{user_id}", "select": "giveaway_number"})
    data = r.json()
    return data[0]["giveaway_number"] if data else None


async def add_user(user_id: int, username: str, first_name: str, last_name: str):
    async with httpx.AsyncClient() as client:
        exists = await client.get(_url("users"), headers=_headers(),
                                  params={"user_id": f"eq.{user_id}", "select": "user_id"})
        if exists.json():
            return
        number = await _next_giveaway_number(client)
        await client.post(_url("users"), headers=_headers("return=minimal"),
                          json={"user_id": user_id, "username": username,
                                "first_name": first_name, "last_name": last_name,
                                "joined_at": datetime.now().isoformat(timespec="seconds"),
                                "giveaway_number": number})


async def get_all_user_ids() -> list[int]:
    async with httpx.AsyncClient() as client:
        r = await client.get(_url("users"), headers=_headers(), params={"select": "user_id"})
    return [row["user_id"] for row in r.json()]


async def save_phone(user_id: int, phone: str):
    async with httpx.AsyncClient() as client:
        await client.patch(_url("users"), headers=_headers("return=minimal"),
                           params={"user_id": f"eq.{user_id}"},
                           json={"phone": phone})


async def get_stats() -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(_url("users"),
                             headers={**_headers(), "Prefer": "count=exact"},
                             params={"select": "*"})
        content_range = r.headers.get("content-range", "0/0")
        total = int(content_range.split("/")[-1]) if "/" in content_range else 0

        r2 = await client.get(_url("users"), headers=_headers(),
                               params={"select": "first_name,username,joined_at",
                                       "order": "id.desc", "limit": "5"})
    recent = [(row["first_name"], row["username"], row["joined_at"])
              for row in r2.json()]
    return {"total": total, "recent": recent}


async def export_csv() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(_url("users"), headers=_headers(),
                             params={"select": "user_id,username,first_name,last_name,phone,joined_at",
                                     "order": "id"})
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "username", "first_name", "last_name", "phone", "joined_at"])
    for row in r.json():
        writer.writerow([row["user_id"], row["username"], row["first_name"],
                         row["last_name"], row["phone"], row["joined_at"]])
    return output.getvalue()
