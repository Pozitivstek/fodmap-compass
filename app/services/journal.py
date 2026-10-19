"""Дневник: добавление еды, сводка дня, запись самочувствия с обновлением личной переносимости."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.clock import day_range, local_today, utcnow
from app.domain import MEALS
from app.services import fodmap, insights, nutrition, streak
from app.services.catalog import Food
from app.services.foodview import from_snapshot, snapshot, to_tolerance
from app.services.report import build_pdf
from app.services.tolerance import apply_reaction, is_bad, pick_suspects
from app.storage import Storage
from app.storage.diary import DiaryEntry
from app.storage.users import User

STATS_WINDOW_DAYS = 60
DUPLICATE_WINDOW = timedelta(seconds=15)
WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


@dataclass(frozen=True)
class EntryView:
    entry: DiaryEntry
    verdict: fodmap.Verdict

    def to_dict(self) -> dict:
        return {**self.entry.to_dict(), "verdict": self.verdict.to_dict()}


def today_for(user: User) -> str:
    return local_today(user.tz).isoformat()


async def add_entry(storage: Storage, user: User, food: Food, day: str, meal: str, grams: float) -> int:
    profile = fodmap.Profile.from_settings(user.data)
    tolerance = to_tolerance(await storage.tolerances.get(user.id, food.ref))
    verdict = fodmap.evaluate(food, profile, grams, tolerance)
    entry_id = await storage.diary.add(user.id, day, meal, food.ref, food.name, food.emoji, grams,
                                       nutrition.macros(food, grams), snapshot(food, verdict.loads))
    reminders = user.setting("reminders") or {}
    delay = int(reminders.get("after_meal_minutes") or 0)
    if reminders.get("enabled") and delay > 0 and day == today_for(user):
        await storage.extras.schedule_prompt(user.id, day, meal, utcnow() + timedelta(minutes=delay))
    return entry_id


async def update_entry(storage: Storage, user: User, entry: DiaryEntry, grams: float, meal: str) -> None:
    food = from_snapshot(entry.ref, entry.name, entry.emoji, entry.food)
    tolerance = to_tolerance(await storage.tolerances.get(user.id, entry.ref))
    verdict = fodmap.evaluate(food, fodmap.Profile.from_settings(user.data), grams, tolerance)
    await storage.diary.update(user.id, entry.id, grams, meal, nutrition.macros(food, grams),
                               snapshot(food, verdict.loads))


def _evaluate_entry(entry: DiaryEntry, profile: fodmap.Profile, tolerances: dict) -> EntryView:
    food = from_snapshot(entry.ref, entry.name, entry.emoji, entry.food)
    verdict = fodmap.evaluate(food, profile, entry.grams, to_tolerance(tolerances.get(entry.ref)))
    return EntryView(entry=entry, verdict=verdict)


async def day_summary(storage: Storage, user: User, day: str) -> dict:
    profile = fodmap.Profile.from_settings(user.data)
    tolerances = await storage.tolerances.all(user.id)
    views = [_evaluate_entry(e, profile, tolerances) for e in await storage.diary.by_day(user.id, day)]
    reactions = await storage.reactions.between(user.id, day, day)
    meals = {}
    for code, spec in MEALS.items():
        items = [v for v in views if v.entry.meal == code]
        meals[code] = {
            **spec, "code": code, "entries": [v.to_dict() for v in items],
            "totals": nutrition.total([v.entry.macros for v in items]),
            "stack": fodmap.stack([v.verdict.loads for v in items]),
            "reactions": [r.to_dict() for r in reactions if r.meal == code],
        }
    body = user.setting("body") or {}
    return {
        "day": day, "meals": meals,
        "totals": nutrition.total([v.entry.macros for v in views]),
        "targets": nutrition.targets(body, user.setting("targets_override")),
        "stack": fodmap.stack([v.verdict.loads for v in views]),
        "reactions": [r.to_dict() for r in reactions],
        "water": {"ml": await storage.extras.water(user.id, day),
                  "goal": int(user.setting("water_goal_ml") or nutrition.water_goal(body, 2000))},
    }


def _risky(entry: DiaryEntry, profile: fodmap.Profile) -> bool:
    food = entry.food
    groups = set(food.get("groups") or ()) & profile.fodmap_groups
    allergens = set(food.get("allergens") or ()) & profile.allergens
    return bool(groups or allergens)


async def _recent_duplicate(storage: Storage, user: User, day: str, meal: str | None, ref: str | None,
                            feeling: str) -> int | None:
    """Двойное нажатие не должно дважды засчитать реакцию в личную переносимость."""
    for reaction in reversed(await storage.reactions.between(user.id, day, day)):
        same = (reaction.meal, reaction.ref, reaction.feeling) == (meal, ref, feeling)
        if same and utcnow() - datetime.fromisoformat(reaction.created_at) < DUPLICATE_WINDOW:
            return reaction.id
    return None


async def record_reaction(storage: Storage, user: User, *, day: str, meal: str | None, ref: str | None,
                          feeling: str, symptoms: list[str], severity: int, note: str,
                          ref_name: str = "", grams: float | None = None) -> dict:
    """Сохраняет реакцию и обновляет личную отметку у продуктов, которые могли её вызвать."""
    duplicate = await _recent_duplicate(storage, user, day, meal, ref, feeling)
    if duplicate is not None:
        return {"id": duplicate, "updated": [], "duplicate": True}
    profile = fodmap.Profile.from_settings(user.data)
    entries = await storage.diary.by_day(user.id, day)
    if ref:
        matching = [e for e in entries if e.ref == ref]
        foods = [(ref, ref_name or (matching[0].name if matching else ref),
                  grams or (matching[-1].grams if matching else None), True)]
    else:
        scoped = [e for e in entries if meal is None or e.meal == meal]
        foods = [(e.ref, e.name, e.grams, _risky(e, profile)) for e in scoped]
    effective = "bad" if (feeling in ("great", "ok") and is_bad(feeling, severity)) else feeling
    suspects = pick_suspects(foods, effective)
    reaction_id = await storage.reactions.add(user.id, day, meal, ref, feeling, symptoms, severity, note,
                                              [s[0] for s in suspects])
    updated = []
    for suspect_ref, name, amount in suspects:
        record = apply_reaction(await storage.tolerances.get(user.id, suspect_ref), suspect_ref, name,
                                effective, amount)
        await storage.tolerances.save(user.id, record)
        updated.append(record.to_dict())
    if meal:
        await storage.extras.answer_prompts(user.id, day, meal)
    return {"id": reaction_id, "updated": updated}


async def stats(storage: Storage, user: User) -> dict:
    today = local_today(user.tz)
    days = await storage.diary.days(user.id)
    run = streak.compute(days, today)
    start = (today - timedelta(days=STATS_WINDOW_DAYS)).isoformat()
    water = await storage.extras.water_between(user.id, start, today.isoformat())
    goal = int(user.setting("water_goal_ml") or 2000)
    counters = user.setting("stats") or {}
    values = {
        "entries": await storage.diary.count(user.id), "best_streak": run.best,
        "reactions": await storage.reactions.count(user.id),
        "tested": len(await storage.tolerances.all(user.id)),
        "scans": counters.get("scans", 0), "recipes_logged": counters.get("recipes_logged", 0),
        "water_days": sum(ml >= goal for ml in water.values()),
    }
    week = [{"day": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "logged": d.isoformat() in days}
            for d in day_range(today, 7)]
    return {"streak": run.to_dict(), "values": values, "achievements": streak.achievements(values), "week": week}


async def period_data(storage: Storage, user: User, days: int) -> tuple[dict, list, list, str]:
    """Аналитика за последние days дней: (insights, записи, реакции, «дд.мм.гггг — дд.мм.гггг»)."""
    today = local_today(user.tz)
    start = today - timedelta(days=days - 1)
    entries = await storage.diary.between(user.id, start.isoformat(), today.isoformat())
    reactions = await storage.reactions.between(user.id, start.isoformat(), today.isoformat())
    water = await storage.extras.water_between(user.id, start.isoformat(), today.isoformat())
    data = insights.build([d.isoformat() for d in day_range(today, days)], entries, reactions, water)
    return data, entries, reactions, f"{start.strftime('%d.%m.%Y')} — {today.strftime('%d.%m.%Y')}"


async def report_pdf(storage: Storage, user: User, days: int) -> tuple[bytes, str, str]:
    """PDF-отчёт: (байты, имя файла, период). Бросает ReportError, если нет шрифта."""
    data, entries, reactions, period = await period_data(storage, user, days)
    tolerances = list((await storage.tolerances.all(user.id)).values())
    pdf = build_pdf(name=user.first_name, period=period, conditions=user.setting("conditions") or [],
                    insights=data, entries=entries, reactions=reactions, tolerances=tolerances)
    return pdf, f"fodmap-report-{local_today(user.tz).isoformat()}.pdf", period
