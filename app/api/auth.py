"""Проверка initData мини-приложения Telegram (HMAC-SHA256 по токену бота)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    """Подпись initData неверна или устарела."""


def _secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign(fields: dict[str, str], bot_token: str) -> str:
    """Подписывает поля так же, как Telegram (нужно для тестов)."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    return hmac.new(_secret(bot_token), check.encode(), hashlib.sha256).hexdigest()


def validate(init_data: str, bot_token: str, ttl_seconds: int, now: float | None = None) -> dict:
    if not init_data or not bot_token:
        raise InitDataError("нет данных авторизации")
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received = fields.pop("hash", "")
    if not received or not received.isascii() or not hmac.compare_digest(sign(fields, bot_token), received):
        raise InitDataError("подпись не совпадает")
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("неверная дата") from exc
    if (now or time.time()) - auth_date > ttl_seconds:
        raise InitDataError("сессия устарела, откройте приложение заново")
    try:
        user = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise InitDataError("неверный пользователь") from exc
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise InitDataError("нет пользователя")
    return user
