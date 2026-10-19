"""Вода, свои продукты, кеш Open Food Facts, напоминания и список покупок."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import aiosqlite

from app.clock import utc_iso, utcnow

OFF_CACHE_TTL = timedelta(days=14)
MAX_WATER_ML = 10_000


class ExtrasRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    # ---- вода ----
    async def water(self, user_id: int, day: str) -> int:
        async with self._conn.execute("SELECT ml FROM water WHERE user_id = ? AND day = ?", (user_id, day)) as cur:
            row = await cur.fetchone()
        return int(row["ml"]) if row else 0

    async def add_water(self, user_id: int, day: str, delta_ml: int) -> int:
        current = await self.water(user_id, day)
        new_value = max(0, min(MAX_WATER_ML, current + delta_ml))
        await self._conn.execute(
            "INSERT INTO water (user_id, day, ml) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, day) DO UPDATE SET ml = excluded.ml", (user_id, day, new_value))
        await self._conn.commit()
        return new_value

    async def water_between(self, user_id: int, start: str, end: str) -> dict[str, int]:
        async with self._conn.execute("SELECT day, ml FROM water WHERE user_id = ? AND day BETWEEN ? AND ?",
                                      (user_id, start, end)) as cur:
            rows = await cur.fetchall()
        return {row["day"]: int(row["ml"]) for row in rows}

    # ---- свои продукты ----
    async def add_custom_food(self, user_id: int, data: dict) -> int:
        cur = await self._conn.execute("INSERT INTO custom_foods (user_id, data, created_at) VALUES (?, ?, ?)",
                                       (user_id, json.dumps(data, ensure_ascii=False), utc_iso()))
        await self._conn.commit()
        return int(cur.lastrowid)

    async def custom_food(self, user_id: int, food_id: int) -> dict | None:
        async with self._conn.execute("SELECT id, data FROM custom_foods WHERE id = ? AND user_id = ?",
                                      (food_id, user_id)) as cur:
            row = await cur.fetchone()
        return {**json.loads(row["data"]), "id": row["id"]} if row else None

    async def custom_foods(self, user_id: int) -> list[dict]:
        async with self._conn.execute("SELECT id, data FROM custom_foods WHERE user_id = ? ORDER BY id DESC",
                                      (user_id,)) as cur:
            rows = await cur.fetchall()
        return [{**json.loads(row["data"]), "id": row["id"]} for row in rows]

    async def delete_custom_food(self, user_id: int, food_id: int) -> bool:
        cur = await self._conn.execute("DELETE FROM custom_foods WHERE id = ? AND user_id = ?", (food_id, user_id))
        await self._conn.commit()
        return cur.rowcount > 0

    # ---- кеш Open Food Facts ----
    async def off_get(self, code: str) -> dict | None:
        async with self._conn.execute("SELECT data, fetched_at FROM off_cache WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
        if not row or utcnow() - datetime.fromisoformat(row["fetched_at"]) > OFF_CACHE_TTL:
            return None
        return json.loads(row["data"])

    async def off_put(self, code: str, data: dict) -> None:
        await self._conn.execute(
            "INSERT INTO off_cache (code, data, fetched_at) VALUES (?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET data = excluded.data, fetched_at = excluded.fetched_at",
            (code, json.dumps(data, ensure_ascii=False), utc_iso()))
        await self._conn.commit()

    async def off_prune(self) -> int:
        cutoff = utc_iso(utcnow() - OFF_CACHE_TTL)
        cur = await self._conn.execute("DELETE FROM off_cache WHERE fetched_at < ?", (cutoff,))
        await self._conn.commit()
        return cur.rowcount

    # ---- вопросы «как самочувствие» после еды ----
    async def schedule_prompt(self, user_id: int, day: str, meal: str, due_at: datetime) -> None:
        await self._conn.execute(
            "INSERT INTO prompts (user_id, day, meal, due_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, day, meal) DO UPDATE SET due_at = excluded.due_at WHERE prompts.sent = 0",
            (user_id, day, meal, utc_iso(due_at)))
        await self._conn.commit()

    async def due_prompts(self, now: datetime) -> list[dict]:
        async with self._conn.execute(
            "SELECT * FROM prompts WHERE sent = 0 AND answered = 0 AND due_at <= ? ORDER BY due_at",
            (utc_iso(now),)) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def prompt(self, prompt_id: int) -> dict | None:
        async with self._conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def mark_prompt(self, prompt_id: int, *, sent: bool | None = None, answered: bool | None = None) -> None:
        if sent is not None:
            await self._conn.execute("UPDATE prompts SET sent = ? WHERE id = ?", (int(sent), prompt_id))
        if answered is not None:
            await self._conn.execute("UPDATE prompts SET answered = ? WHERE id = ?", (int(answered), prompt_id))
        await self._conn.commit()

    async def answer_prompts(self, user_id: int, day: str, meal: str) -> None:
        await self._conn.execute("UPDATE prompts SET answered = 1 WHERE user_id = ? AND day = ? AND meal = ?",
                                 (user_id, day, meal))
        await self._conn.commit()

    async def remind_once(self, user_id: int, kind: str, day: str) -> bool:
        """True, если напоминание этого вида сегодня ещё не отправлялось (и отмечает его)."""
        cur = await self._conn.execute(
            "INSERT OR IGNORE INTO reminder_log (user_id, kind, day) VALUES (?, ?, ?)", (user_id, kind, day))
        await self._conn.commit()
        return cur.rowcount > 0

    # ---- список покупок ----
    async def shopping(self, user_id: int) -> list[dict]:
        async with self._conn.execute(
            "SELECT id, name, ref, done FROM shopping WHERE user_id = ? ORDER BY done, id DESC", (user_id,)) as cur:
            rows = await cur.fetchall()
        return [{"id": r["id"], "name": r["name"], "ref": r["ref"], "done": bool(r["done"])} for r in rows]

    async def add_shopping(self, user_id: int, items: list[tuple[str, str]]) -> None:
        existing = {item["name"].lower() for item in await self.shopping(user_id) if not item["done"]}
        fresh = [(name, ref) for name, ref in items if name.lower() not in existing]
        await self._conn.executemany(
            "INSERT INTO shopping (user_id, name, ref, created_at) VALUES (?, ?, ?, ?)",
            [(user_id, name, ref, utc_iso()) for name, ref in fresh])
        await self._conn.commit()

    async def set_shopping_done(self, user_id: int, item_id: int, done: bool) -> bool:
        cur = await self._conn.execute("UPDATE shopping SET done = ? WHERE id = ? AND user_id = ?",
                                       (int(done), item_id, user_id))
        await self._conn.commit()
        return cur.rowcount > 0

    async def delete_shopping(self, user_id: int, item_id: int | None = None) -> None:
        if item_id is None:
            await self._conn.execute("DELETE FROM shopping WHERE user_id = ? AND done = 1", (user_id,))
        else:
            await self._conn.execute("DELETE FROM shopping WHERE id = ? AND user_id = ?", (item_id, user_id))
        await self._conn.commit()
