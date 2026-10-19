"""Контекст приложения и зависимости FastAPI: текущий пользователь, лимиты запросов."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from fastapi import Depends, Header, HTTPException, Request, status

from app.api.auth import InitDataError, validate
from app.config import Settings
from app.services.catalog import Catalog
from app.services.foodview import FoodResolver
from app.services.off import OpenFoodFacts
from app.storage import Storage
from app.storage.users import User

log = logging.getLogger(__name__)

SendDocument = Callable[[int, bytes, str, str], Awaitable[None]]


class RateLimiter:
    """Скользящее окно в памяти: не больше limit запросов за window секунд на ключ."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        moment = now or time.monotonic()
        hits = self._hits[key]
        while hits and moment - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(moment)
        return True


@dataclass
class AppContext:
    settings: Settings
    storage: Storage
    catalog: Catalog
    off: OpenFoodFacts
    resolver: FoodResolver
    send_document: SendDocument | None = None
    limiters: dict[str, RateLimiter] = field(default_factory=lambda: {
        "external": RateLimiter(limit=30, window=60), "write": RateLimiter(limit=120, window=60),
        "report": RateLimiter(limit=3, window=600),
    })


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def current_user(ctx: AppContext = Depends(get_ctx),
                       init_data: str = Header(default="", alias="X-Telegram-Init-Data")) -> User:
    settings = ctx.settings
    if not init_data and settings.dev_mode:
        return await ctx.storage.users.ensure(settings.dev_user_id, "Разработчик", "dev")
    try:
        tg_user = validate(init_data, settings.bot_token, settings.init_data_ttl)
    except InitDataError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Не удалось войти: {exc}") from exc
    return await ctx.storage.users.ensure(tg_user["id"], tg_user.get("first_name", ""), tg_user.get("username", ""))


def limit(bucket: str):
    async def dependency(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> User:
        if not ctx.limiters[bucket].allow(f"{bucket}:{user.id}"):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком часто. Подождите немного.")
        return user
    return dependency
