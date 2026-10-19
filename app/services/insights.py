"""Аналитика: симптомы по дням, подозреваемые продукты-триггеры, FODMAP-группы."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from app.domain import FEELINGS, FODMAP_GROUPS, SYMPTOMS
from app.services.nutrition import MACROS
from app.storage.diary import DiaryEntry
from app.storage.reactions import Reaction

LOOKBACK = timedelta(hours=6)
MIN_EATEN_FOR_SUSPECT = 2
SUSPECT_RATE = 0.5
TOP_N = 8
GROUP_EXPOSURE_LOAD = 0.5


def reaction_score(reaction: Reaction) -> int:
    """0 — всё хорошо, до 5 — очень плохо."""
    weight = FEELINGS.get(reaction.feeling, {}).get("weight", 0)
    return max(weight * 2, reaction.severity, min(len(reaction.symptoms), 3))


def linked_entries(reaction: Reaction, entries: list[DiaryEntry]) -> list[DiaryEntry]:
    same_day = [e for e in entries if e.day == reaction.day]
    if reaction.refs or reaction.ref:
        refs = set(reaction.refs) | ({reaction.ref} if reaction.ref else set())
        return [e for e in same_day if e.ref in refs]
    if reaction.meal:
        return [e for e in same_day if e.meal == reaction.meal]
    moment = datetime.fromisoformat(reaction.created_at)
    return [e for e in same_day if timedelta(0) <= moment - datetime.fromisoformat(e.created_at) <= LOOKBACK]


def _daily(days: list[str], entries: list[DiaryEntry], reactions: list[Reaction], water: dict[str, int]) -> list:
    kcal = defaultdict(float)
    for entry in entries:
        kcal[entry.day] += entry.macros.get("kcal", 0)
    worst = defaultdict(int)
    for reaction in reactions:
        worst[reaction.day] = max(worst[reaction.day], reaction_score(reaction))
    logged = {e.day for e in entries}
    rated = {r.day for r in reactions}
    return [{"day": d, "kcal": round(kcal[d]), "score": worst[d] if d in rated else None,
             "logged": d in logged, "water": water.get(d, 0)} for d in days]


def _food_stats(entries: list[DiaryEntry], reactions: list[Reaction]) -> tuple[list, list]:
    eaten: Counter = Counter()
    names: dict[str, tuple[str, str]] = {}
    for entry in entries:
        eaten[entry.ref] += 1
        names[entry.ref] = (entry.name, entry.emoji)
    bad: Counter = Counter()
    for reaction in reactions:
        if reaction_score(reaction) < 2:
            continue
        for ref in {e.ref for e in linked_entries(reaction, entries)}:
            bad[ref] += 1
    suspects, safe = [], []
    for ref, count in eaten.items():
        rate = bad[ref] / count
        item = {"ref": ref, "name": names[ref][0], "emoji": names[ref][1], "eaten": count, "bad": bad[ref],
                "rate": round(rate, 2)}
        if count >= MIN_EATEN_FOR_SUSPECT and rate >= SUSPECT_RATE:
            suspects.append(item)
        elif count >= MIN_EATEN_FOR_SUSPECT and bad[ref] == 0:
            safe.append(item)
    suspects.sort(key=lambda i: (-i["rate"], -i["bad"]))
    safe.sort(key=lambda i: -i["eaten"])
    return suspects[:TOP_N], safe[:TOP_N]


def _group_stats(entries: list[DiaryEntry], reactions: list[Reaction]) -> list[dict]:
    exposures: Counter = Counter()
    bad: Counter = Counter()
    for reaction in reactions:
        loads: dict[str, float] = defaultdict(float)
        for entry in linked_entries(reaction, entries):
            for group, value in (entry.food.get("loads") or {}).items():
                loads[group] += value
        for group, value in loads.items():
            if value >= GROUP_EXPOSURE_LOAD:
                exposures[group] += 1
                bad[group] += reaction_score(reaction) >= 2
    return [{"group": g, "name": FODMAP_GROUPS[g]["name"], "exposures": exposures[g], "bad": bad[g],
             "rate": round(bad[g] / exposures[g], 2) if exposures[g] else 0.0}
            for g in FODMAP_GROUPS if exposures[g]]


def _averages(entries: list[DiaryEntry]) -> dict[str, float]:
    per_day: dict[str, dict[str, float]] = defaultdict(lambda: dict.fromkeys(MACROS, 0.0))
    for entry in entries:
        for key in MACROS:
            per_day[entry.day][key] += entry.macros.get(key, 0)
    if not per_day:
        return dict.fromkeys(MACROS, 0.0)
    return {key: round(sum(d[key] for d in per_day.values()) / len(per_day), 1) for key in MACROS}


def build(days: list[str], entries: list[DiaryEntry], reactions: list[Reaction], water: dict[str, int]) -> dict:
    symptoms = Counter(s for r in reactions for s in r.symptoms)
    suspects, safe = _food_stats(entries, reactions)
    scores = [reaction_score(r) for r in reactions]
    return {
        "days": _daily(days, entries, reactions, water),
        "symptoms": [{"code": c, "name": SYMPTOMS[c]["name"], "emoji": SYMPTOMS[c]["emoji"], "count": n}
                     for c, n in symptoms.most_common() if c in SYMPTOMS],
        "suspects": suspects,
        "safe": safe,
        "groups": _group_stats(entries, reactions),
        "averages": _averages(entries),
        "reactions_total": len(reactions),
        "good_share": round(sum(s < 2 for s in scores) / len(scores), 2) if scores else None,
        "logged_days": len({e.day for e in entries}),
    }
