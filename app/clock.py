"""Время: UTC-метки для БД и локальные даты пользователя."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import DEFAULT_TZ


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(moment: datetime | None = None) -> str:
    return (moment or utcnow()).astimezone(timezone.utc).isoformat(timespec="seconds")


def zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def is_valid_tz(tz: str) -> bool:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def local_now(tz: str, moment: datetime | None = None) -> datetime:
    return (moment or utcnow()).astimezone(zone(tz))


def local_today(tz: str, moment: datetime | None = None) -> date:
    return local_now(tz, moment).date()


def parse_day(value: str) -> date:
    return date.fromisoformat(value)


def day_range(end: date, days: int) -> list[date]:
    return [end - timedelta(days=offset) for offset in range(days - 1, -1, -1)]
