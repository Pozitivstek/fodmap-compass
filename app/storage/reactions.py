"""Реакции организма и личная переносимость продуктов."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import aiosqlite

from app.clock import utc_iso


@dataclass(frozen=True)
class Reaction:
    id: int
    day: str
    meal: str | None
    ref: str | None
    feeling: str
    symptoms: tuple[str, ...]
    severity: int
    note: str
    refs: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "day": self.day, "meal": self.meal, "ref": self.ref, "feeling": self.feeling,
                "symptoms": list(self.symptoms), "severity": self.severity, "note": self.note,
                "refs": list(self.refs), "created_at": self.created_at}


@dataclass(frozen=True)
class ToleranceRecord:
    ref: str
    name: str
    status: str
    tested_g: float | None
    ok_count: int
    mild_count: int
    bad_count: int
    manual: bool
    note: str
    updated_at: str

    def to_dict(self) -> dict:
        return {"ref": self.ref, "name": self.name, "status": self.status, "tested_g": self.tested_g,
                "ok_count": self.ok_count, "mild_count": self.mild_count, "bad_count": self.bad_count,
                "manual": self.manual, "note": self.note, "updated_at": self.updated_at}


def _reaction(row: aiosqlite.Row) -> Reaction:
    return Reaction(id=row["id"], day=row["day"], meal=row["meal"], ref=row["ref"], feeling=row["feeling"],
                    symptoms=tuple(json.loads(row["symptoms"] or "[]")), severity=row["severity"],
                    note=row["note"], refs=tuple(json.loads(row["refs"] or "[]")), created_at=row["created_at"])


def _tolerance(row: aiosqlite.Row) -> ToleranceRecord:
    return ToleranceRecord(ref=row["ref"], name=row["name"], status=row["status"], tested_g=row["tested_g"],
                           ok_count=row["ok_count"], mild_count=row["mild_count"], bad_count=row["bad_count"],
                           manual=bool(row["manual"]), note=row["note"], updated_at=row["updated_at"])


class ReactionRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def add(self, user_id: int, day: str, meal: str | None, ref: str | None, feeling: str,
                  symptoms: list[str], severity: int, note: str, refs: list[str]) -> int:
        cur = await self._conn.execute(
            "INSERT INTO reactions (user_id, day, meal, ref, feeling, symptoms, severity, note, refs, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, day, meal, ref, feeling, json.dumps(symptoms), severity, note,
             json.dumps(refs, ensure_ascii=False), utc_iso()),
        )
        await self._conn.commit()
        return int(cur.lastrowid)

    async def delete(self, user_id: int, reaction_id: int) -> bool:
        cur = await self._conn.execute("DELETE FROM reactions WHERE id = ? AND user_id = ?",
                                       (reaction_id, user_id))
        await self._conn.commit()
        return cur.rowcount > 0

    async def between(self, user_id: int, start: str, end: str) -> list[Reaction]:
        async with self._conn.execute(
            "SELECT * FROM reactions WHERE user_id = ? AND day BETWEEN ? AND ? ORDER BY day, created_at, id",
            (user_id, start, end),
        ) as cur:
            rows = await cur.fetchall()
        return [_reaction(row) for row in rows]

    async def for_ref(self, user_id: int, ref: str, limit: int = 20) -> list[Reaction]:
        async with self._conn.execute(
            "SELECT * FROM reactions WHERE user_id = ? AND (ref = ? OR refs LIKE ?) ORDER BY id DESC LIMIT ?",
            (user_id, ref, f'%"{ref}"%', limit),
        ) as cur:
            rows = await cur.fetchall()
        return [_reaction(row) for row in rows]

    async def count(self, user_id: int) -> int:
        async with self._conn.execute("SELECT COUNT(*) AS n FROM reactions WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return int(row["n"])


class ToleranceRepo:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def get(self, user_id: int, ref: str) -> ToleranceRecord | None:
        async with self._conn.execute("SELECT * FROM tolerances WHERE user_id = ? AND ref = ?",
                                      (user_id, ref)) as cur:
            row = await cur.fetchone()
        return _tolerance(row) if row else None

    async def all(self, user_id: int) -> dict[str, ToleranceRecord]:
        async with self._conn.execute("SELECT * FROM tolerances WHERE user_id = ? ORDER BY updated_at DESC",
                                      (user_id,)) as cur:
            rows = await cur.fetchall()
        return {row["ref"]: _tolerance(row) for row in rows}

    async def save(self, user_id: int, record: ToleranceRecord) -> None:
        await self._conn.execute(
            "INSERT INTO tolerances (user_id, ref, name, status, tested_g, ok_count, mild_count, bad_count, "
            "manual, note, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, ref) DO UPDATE SET name = excluded.name, status = excluded.status, "
            "tested_g = excluded.tested_g, ok_count = excluded.ok_count, mild_count = excluded.mild_count, "
            "bad_count = excluded.bad_count, manual = excluded.manual, note = excluded.note, "
            "updated_at = excluded.updated_at",
            (user_id, record.ref, record.name, record.status, record.tested_g, record.ok_count,
             record.mild_count, record.bad_count, int(record.manual), record.note, record.updated_at),
        )
        await self._conn.commit()

    async def delete(self, user_id: int, ref: str) -> bool:
        cur = await self._conn.execute("DELETE FROM tolerances WHERE user_id = ? AND ref = ?", (user_id, ref))
        await self._conn.commit()
        return cur.rowcount > 0
