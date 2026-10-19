"""Серия дней подряд с записями («огонёк») и достижения."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Streak:
    current: int
    best: int
    today_logged: bool
    at_risk: bool

    def to_dict(self) -> dict:
        return {"current": self.current, "best": self.best, "today_logged": self.today_logged,
                "at_risk": self.at_risk}


def _run_back(days: set[date], start: date) -> int:
    length, cursor = 0, start
    while cursor in days:
        length += 1
        cursor -= timedelta(days=1)
    return length


def _best(days: set[date]) -> int:
    """Самая длинная серия: от каждого начала серии считаем вперёд."""
    return max((1 + _forward(days, day) for day in days if day - timedelta(days=1) not in days), default=0)


def _forward(days: set[date], start: date) -> int:
    length, cursor = 0, start + timedelta(days=1)
    while cursor in days:
        length += 1
        cursor += timedelta(days=1)
    return length


def compute(day_strings: set[str], today: date) -> Streak:
    days = {date.fromisoformat(d) for d in day_strings}
    today_logged = today in days
    start = today if today_logged else today - timedelta(days=1)
    current = _run_back(days, start)
    return Streak(current=current, best=max(_best(days), current), today_logged=today_logged,
                  at_risk=current > 0 and not today_logged)


ACHIEVEMENTS: tuple[dict, ...] = (
    {"code": "first_entry", "emoji": "🌱", "title": "Первый шаг", "desc": "Первая запись в дневнике",
     "stat": "entries", "goal": 1},
    {"code": "streak_3", "emoji": "🔥", "title": "Разгорается", "desc": "3 дня подряд", "stat": "best_streak",
     "goal": 3},
    {"code": "streak_7", "emoji": "🔥", "title": "Неделя огня", "desc": "7 дней подряд", "stat": "best_streak",
     "goal": 7},
    {"code": "streak_14", "emoji": "💫", "title": "Две недели", "desc": "14 дней подряд", "stat": "best_streak",
     "goal": 14},
    {"code": "streak_30", "emoji": "🏆", "title": "Месяц дисциплины", "desc": "30 дней подряд",
     "stat": "best_streak", "goal": 30},
    {"code": "streak_100", "emoji": "👑", "title": "Легенда", "desc": "100 дней подряд", "stat": "best_streak",
     "goal": 100},
    {"code": "listener", "emoji": "👂", "title": "Слушаю себя", "desc": "10 записей о самочувствии",
     "stat": "reactions", "goal": 10},
    {"code": "explorer", "emoji": "🧪", "title": "Исследователь", "desc": "Проверить переносимость 10 продуктов",
     "stat": "tested", "goal": 10},
    {"code": "scanner", "emoji": "📷", "title": "Сканер", "desc": "Отсканировать 5 товаров", "stat": "scans",
     "goal": 5},
    {"code": "chef", "emoji": "👩‍🍳", "title": "Шеф", "desc": "Приготовить 5 рецептов", "stat": "recipes_logged",
     "goal": 5},
    {"code": "hydrated", "emoji": "💧", "title": "Водный баланс", "desc": "7 дней с нормой воды",
     "stat": "water_days", "goal": 7},
    {"code": "hundred", "emoji": "📒", "title": "Летописец", "desc": "100 записей о еде", "stat": "entries",
     "goal": 100},
)


def achievements(stats: dict[str, int]) -> list[dict]:
    result = []
    for spec in ACHIEVEMENTS:
        value = int(stats.get(spec["stat"], 0))
        result.append({"code": spec["code"], "emoji": spec["emoji"], "title": spec["title"], "desc": spec["desc"],
                       "earned": value >= spec["goal"], "progress": min(value, spec["goal"]), "goal": spec["goal"]})
    return result
