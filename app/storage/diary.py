"""Дневник питания: записи «что и сколько съел»."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import aiosqlite

from app.clock import utc_iso

MACRO_KEYS = ("kcal", "protein", "fat", "carbs", "fiber")


@dataclass(frozen=True)
class DiaryEntry:
    id: int
    day: str
    meal: str
    ref: str
    name: str
    emoji: str
    grams: float
    macros: dict
    food: dict = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "day": self.day, "meal": self.meal, "ref": self.ref, "name": self.name,
                "emoji": self.emoji, "grams": self.grams, "macros": self.macros, "created_at": self.created_at}


def _row(row: aiosqlite.Row) -> DiaryEntry:
    return DiaryEntry(
        id=row["id"], day=row["day"], meal=row["meal"], ref=row["ref"], name=row["name"], emoji=row["emoji"],
        grams=row["grams"], macros={key: row[key] for key in MACRO_KEYS},
        food=json.loads(row["food"] or "{}"), created_at=row["created_at"],
    )


class DiaryRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def add(self, user_id: int, day: str, meal: str, ref: str, name: str, emoji: str,
                  grams: float, macros: dict, food: dict) -> int:
        cur = await self._conn.execute(
            "INSERT INTO diary (user_id, day, meal, ref, name, emoji, grams, kcal, protein, fat, carbs, fiber, "
            "food, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, day, meal, ref, name, emoji, grams, *(macros.get(k, 0) for k in MACRO_KEYS),
             json.dumps(food, ensure_ascii=False), utc_iso()),
        )
        await self._conn.commit()
        return int(cur.lastrowid)

    async def get(self, user_id: int, entry_id: int) -> DiaryEntry | None:
        async with self._conn.execute("SELECT * FROM diary WHERE id = ? AND user_id = ?",
                                      (entry_id, user_id)) as cur:
            row = await cur.fetchone()
        return _row(row) if row else None

    async def update(self, user_id: int, entry_id: int, grams: float, meal: str, macros: dict, food: dict) -> None:
        await self._conn.execute(
            "UPDATE diary SET grams = ?, meal = ?, kcal = ?, protein = ?, fat = ?, carbs = ?, fiber = ?, food = ? "
            "WHERE id = ? AND user_id = ?",
            (grams, meal, *(macros.get(k, 0) for k in MACRO_KEYS), json.dumps(food, ensure_ascii=False),
             entry_id, user_id),
        )
        await self._conn.commit()

    async def delete(self, user_id: int, entry_id: int) -> bool:
        cur = await self._conn.execute("DELETE FROM diary WHERE id = ? AND user_id = ?", (entry_id, user_id))
        await self._conn.commit()
        return cur.rowcount > 0

    async def by_day(self, user_id: int, day: str) -> list[DiaryEntry]:
        return await self.between(user_id, day, day)

    async def between(self, user_id: int, start: str, end: str) -> list[DiaryEntry]:
        async with self._conn.execute(
            "SELECT * FROM diary WHERE user_id = ? AND day BETWEEN ? AND ? ORDER BY day, created_at, id",
            (user_id, start, end),
        ) as cur:
            rows = await cur.fetchall()
        return [_row(row) for row in rows]

    async def days(self, user_id: int) -> set[str]:
        async with self._conn.execute("SELECT DISTINCT day FROM diary WHERE user_id = ?", (user_id,)) as cur:
            rows = await cur.fetchall()
        return {row["day"] for row in rows}

    async def count(self, user_id: int) -> int:
        async with self._conn.execute("SELECT COUNT(*) AS n FROM diary WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return int(row["n"])

    async def recent(self, user_id: int, limit: int = 12) -> list[DiaryEntry]:
        async with self._conn.execute(
            "SELECT * FROM diary WHERE id IN (SELECT MAX(id) FROM diary WHERE user_id = ? GROUP BY ref) "
            "ORDER BY id DESC LIMIT ?", (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [_row(row) for row in rows]
