"""Пользователи и их настройки (JSON в колонке data)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

import aiosqlite

from app.clock import utc_iso

DEFAULT_REMINDERS = {
    "enabled": True,
    "meals": {"breakfast": "09:00", "lunch": "13:30", "dinner": "19:00"},
    "water": True,
    "evening": True,
    "after_meal_minutes": 150,
}

DEFAULT_DATA = {
    "conditions": [],
    "diet_style": "omnivore",
    "dislikes": [],
    "likes": [],
    "tolerated_groups": [],
    "body": {},
    "targets_override": {},
    "water_goal_ml": 2000,
    "theme": "auto",
    "reminders": DEFAULT_REMINDERS,
    "stats": {"scans": 0, "recipes_logged": 0},
    "seen_achievements": [],
}


@dataclass(frozen=True)
class User:
    id: int
    first_name: str
    username: str
    tz: str
    onboarded: bool
    data: dict = field(default_factory=dict)

    def setting(self, key: str):
        return self.data.get(key, DEFAULT_DATA.get(key))


def _merge(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _row_to_user(row: aiosqlite.Row) -> User:
    data = _merge(DEFAULT_DATA, json.loads(row["data"] or "{}"))
    return User(id=row["id"], first_name=row["first_name"], username=row["username"], tz=row["tz"],
                onboarded=bool(row["onboarded"]), data=data)


class UserRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def get(self, user_id: int) -> User | None:
        async with self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def ensure(self, user_id: int, first_name: str = "", username: str = "") -> User:
        now = utc_iso()
        await self._conn.execute(
            "INSERT INTO users (id, first_name, username, data, created_at, last_seen) VALUES (?, ?, ?, '{}', ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen, "
            "first_name = CASE WHEN excluded.first_name != '' THEN excluded.first_name ELSE users.first_name END, "
            "username = CASE WHEN excluded.username != '' THEN excluded.username ELSE users.username END",
            (user_id, first_name, username, now, now),
        )
        await self._conn.commit()
        user = await self.get(user_id)
        assert user is not None
        return user

    async def update(self, user: User, patch: dict, tz: str | None = None, onboarded: bool | None = None) -> User:
        # Сливаем с актуальной строкой, а не со снимком: иначе параллельное сохранение профиля откатится.
        user = await self.get(user.id) or user
        data = _merge(user.data, patch)
        new_user = replace(user, data=data, tz=tz or user.tz,
                           onboarded=user.onboarded if onboarded is None else onboarded)
        await self._conn.execute(
            "UPDATE users SET data = ?, tz = ?, onboarded = ? WHERE id = ?",
            (json.dumps(data, ensure_ascii=False), new_user.tz, int(new_user.onboarded), user.id),
        )
        await self._conn.commit()
        return new_user

    async def bump_stat(self, user: User, key: str, delta: int = 1) -> User:
        user = await self.get(user.id) or user
        stats = dict(user.setting("stats") or {})
        stats[key] = int(stats.get(key, 0)) + delta
        return await self.update(user, {"stats": stats})

    async def all_onboarded(self) -> list[User]:
        async with self._conn.execute("SELECT * FROM users WHERE onboarded = 1") as cur:
            rows = await cur.fetchall()
        return [_row_to_user(row) for row in rows]

    async def delete(self, user_id: int) -> None:
        await self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await self._conn.commit()
