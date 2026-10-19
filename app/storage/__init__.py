"""Слой хранения: репозитории поверх одного соединения SQLite."""

from __future__ import annotations

from dataclasses import dataclass

import aiosqlite

from app.storage.diary import DiaryRepo
from app.storage.extras import ExtrasRepo
from app.storage.reactions import ReactionRepo, ToleranceRepo
from app.storage.users import UserRepo


@dataclass(frozen=True)
class Storage:
    conn: aiosqlite.Connection
    users: UserRepo
    diary: DiaryRepo
    reactions: ReactionRepo
    tolerances: ToleranceRepo
    extras: ExtrasRepo

    @classmethod
    def create(cls, conn: aiosqlite.Connection) -> "Storage":
        return cls(conn=conn, users=UserRepo(conn), diary=DiaryRepo(conn), reactions=ReactionRepo(conn),
                   tolerances=ToleranceRepo(conn), extras=ExtrasRepo(conn))
