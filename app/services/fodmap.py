"""Оценка продукта и порции для конкретного человека: FODMAP, аллергены, личный опыт."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain import ALLERGENS, CONDITIONS, DIET_STYLES, FODMAP_GROUPS, TOLERANCE_STATUSES
from app.services.catalog import Food

GREEN, YELLOW, RED, GREY = "green", "yellow", "red", "grey"
LEVEL_TITLES = {GREEN: "Можно", YELLOW: "Осторожно", RED: "Нельзя", GREY: "Не для вас"}
LEVEL_ORDER = {GREEN: 0, GREY: 1, YELLOW: 2, RED: 3}
# Нагрузка группы в «зелёных порциях»: 1.0 — ровно безопасная порция.
NO_SAFE_PORTION_LOAD = 3.0
STACK_CAUTION = 1.0
STACK_HIGH = 2.0
DEFAULT_HIGH_FACTOR = 2.0


@dataclass(frozen=True)
class Profile:
    conditions: tuple[str, ...] = ()
    diet_style: str = "omnivore"
    dislikes: tuple[str, ...] = ()
    tolerated_groups: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls, data: dict) -> "Profile":
        return cls(conditions=tuple(data.get("conditions") or ()), diet_style=data.get("diet_style") or "omnivore",
                   dislikes=tuple(str(d).lower() for d in data.get("dislikes") or ()),
                   tolerated_groups=tuple(data.get("tolerated_groups") or ()))

    @property
    def fodmap_groups(self) -> frozenset[str]:
        groups = {g for c in self.conditions if (spec := CONDITIONS.get(c)) and spec["kind"] == "portion"
                  for g in spec["groups"]}
        return frozenset(groups - set(self.tolerated_groups))

    @property
    def allergens(self) -> frozenset[str]:
        return frozenset(a for c in self.conditions if (spec := CONDITIONS.get(c)) and spec["kind"] == "allergy"
                         for a in spec["allergens"])

    @property
    def excluded_tags(self) -> frozenset[str]:
        return frozenset(DIET_STYLES.get(self.diet_style, DIET_STYLES["omnivore"])["exclude"])


@dataclass(frozen=True)
class Tolerance:
    status: str
    tested_g: float | None = None
    note: str = ""
    ok_count: int = 0
    bad_count: int = 0


@dataclass(frozen=True)
class Verdict:
    level: str
    title: str
    reasons: tuple[str, ...]
    safe_g: float | None
    grams: float
    loads: dict[str, float] = field(default_factory=dict)
    personal: str | None = None
    allergy: bool = False
    disliked: bool = False

    def to_dict(self) -> dict:
        return {
            "level": self.level, "title": self.title, "reasons": list(self.reasons),
            "safe_g": self.safe_g, "grams": self.grams,
            "loads": {g: round(v, 2) for g, v in self.loads.items()},
            "personal": self.personal, "allergy": self.allergy, "disliked": self.disliked,
        }


def worst(levels: list[str]) -> str:
    return max(levels, key=LEVEL_ORDER.__getitem__, default=GREEN)


def relevant_groups(food: Food, profile: Profile) -> tuple[str, ...]:
    return tuple(g for g in food.groups if g in profile.fodmap_groups)


def group_loads(food: Food, grams: float, groups: tuple[str, ...]) -> dict[str, float]:
    if not groups or grams <= 0:
        return {}
    if food.low_g is None or food.low_g <= 0:
        return {g: NO_SAFE_PORTION_LOAD for g in groups}
    return {g: grams / food.low_g for g in groups}


def portion_level(food: Food, grams: float, groups: tuple[str, ...]) -> tuple[str, str]:
    """Светофор порции только по FODMAP (без аллергенов и личного опыта)."""
    if not groups:
        return GREEN, "FODMAP не обнаружены" if food.fodmap_free else "Не влияет на ваши ограничения"
    names = ", ".join(FODMAP_GROUPS[g]["name"].lower() for g in groups)
    if food.estimated:
        return (RED if food.low_g is None else YELLOW), f"По составу похоже на источник: {names}"
    if food.low_g is None:
        return RED, f"Высокий FODMAP ({names}) в любой порции"
    high = food.high_g or food.low_g * DEFAULT_HIGH_FACTOR
    if grams <= food.low_g:
        return GREEN, f"Низкий FODMAP в порции {grams:g} г"
    if grams < high:
        return YELLOW, f"Больше {food.low_g:g} г растёт нагрузка: {names}"
    return RED, f"С {high:g} г — высокий FODMAP ({names})"


def _personal_override(tolerance: Tolerance, grams: float) -> tuple[str, str]:
    label = TOLERANCE_STATUSES[tolerance.status]["name"]
    if tolerance.status == "avoid":
        return RED, f"{label}: по вашим записям вызывает симптомы"
    if tolerance.status == "caution":
        return YELLOW, f"{label}: были небольшие реакции"
    if tolerance.tested_g and grams > tolerance.tested_g:
        return YELLOW, f"Вам подходило до {tolerance.tested_g:g} г — больше пока не проверяли"
    return GREEN, f"{label} — проверено вами" + (f" ({tolerance.tested_g:g} г)" if tolerance.tested_g else "")


def evaluate(food: Food, profile: Profile, grams: float | None = None,
             tolerance: Tolerance | None = None) -> Verdict:
    amount = grams if grams and grams > 0 else food.portion.grams
    reasons: list[str] = []
    levels: list[str] = []

    hit = sorted(set(food.allergens) & profile.allergens)
    if hit:
        reasons.append("Содержит: " + ", ".join(ALLERGENS[a].lower() for a in hit))
        levels.append(RED)

    if food.unknown and not hit:
        reasons.append("Состав неизвестен — проверьте упаковку перед едой")
        levels.append(YELLOW)

    groups = relevant_groups(food, profile)
    lactose_free = "lactose_free" in food.tags
    if lactose_free:
        groups = tuple(g for g in groups if g != "lac")
    fodmap_level, fodmap_reason = portion_level(food, amount, groups)
    personal = None
    if tolerance and not hit:
        fodmap_level, fodmap_reason = _personal_override(tolerance, amount)
        personal = tolerance.status
    elif lactose_free and fodmap_level == GREEN:
        fodmap_reason = "Без лактозы — подходит"
    levels.append(fodmap_level)
    if groups or personal or not (hit or food.unknown):
        reasons.append(fodmap_reason)

    excluded = sorted(set(food.tags) & profile.excluded_tags)
    if excluded and not hit:
        reasons.append(f"Не входит в ваш рацион: {DIET_STYLES[profile.diet_style]['name'].lower()}")
        levels.append(GREY)

    disliked = food.id in profile.dislikes or any(word in food.name.lower() for word in profile.dislikes
                                                   if len(word) > 3)
    if disliked:
        reasons.append("Вы отметили, что не любите это")

    level = worst(levels)
    safe_g = food.low_g if groups and food.low_g is not None and not hit else None
    if groups and food.low_g is None:
        safe_g = 0.0
    # Проверенная лично порция не добавляет нагрузку в «накопление».
    tolerated = personal == "ok" and fodmap_level == GREEN
    loads = {} if tolerated else group_loads(food, amount, groups)
    return Verdict(level=level, title=LEVEL_TITLES[level], reasons=tuple(reasons), safe_g=safe_g,
                   grams=amount, loads=loads, personal=personal, allergy=bool(hit), disliked=disliked)


def stack(loads: list[dict[str, float]]) -> dict:
    """Суммирует FODMAP-нагрузку нескольких продуктов (приём пищи или день)."""
    totals: dict[str, float] = {}
    for item in loads:
        for group, value in item.items():
            totals[group] = totals.get(group, 0.0) + value
    peak = max(totals.values(), default=0.0)
    level = RED if peak > STACK_HIGH else YELLOW if peak > STACK_CAUTION else GREEN
    over = [FODMAP_GROUPS[g]["name"] for g, v in sorted(totals.items(), key=lambda kv: -kv[1])
            if v > STACK_CAUTION]
    short = "Нагрузка в норме" if not over else "Накопление: " + ", ".join(over).lower()
    message = short if not over else short + " — несколько порций сложились в одну большую"
    return {"level": level, "groups": {g: round(v, 2) for g, v in totals.items()}, "short": short,
            "message": message}
