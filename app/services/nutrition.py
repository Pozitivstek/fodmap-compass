"""КБЖУ порций и суточные нормы (формула Миффлина — Сан Жеора)."""

from __future__ import annotations

from datetime import date

from app.domain import ACTIVITY, GOALS
from app.services.catalog import Food

MACROS = ("kcal", "protein", "fat", "carbs", "fiber")
DEFAULT_TARGETS = {"kcal": 2000, "protein": 90, "fat": 67, "carbs": 250, "fiber": 25}
PROTEIN_PER_KG = 1.4
FAT_SHARE = 0.3
KCAL_PER_G = {"protein": 4, "fat": 9, "carbs": 4}
WATER_ML_PER_KG = 30
FIBER_PER_1000_KCAL = 14


def macros(food: Food, grams: float) -> dict[str, float]:
    factor = grams / 100
    values = {"kcal": food.kcal, "protein": food.protein, "fat": food.fat, "carbs": food.carbs,
              "fiber": food.fiber}
    return {key: round(value * factor, 1) for key, value in values.items()}


def total(items: list[dict[str, float]]) -> dict[str, float]:
    return {key: round(sum(item.get(key, 0) for item in items), 1) for key in MACROS}


def _age(birth_year: int | None, today: date) -> int | None:
    return today.year - birth_year if birth_year else None


def targets(body: dict, override: dict | None = None, today: date | None = None) -> dict[str, float]:
    """Нормы на день. Без данных о теле — усреднённые значения."""
    today = today or date.today()
    weight, height = body.get("weight"), body.get("height")
    age = _age(body.get("birth_year"), today)
    result = dict(DEFAULT_TARGETS)
    if weight and height and age:
        sex_shift = 5 if body.get("sex") == "male" else -161
        bmr = 10 * weight + 6.25 * height - 5 * age + sex_shift
        activity = ACTIVITY.get(body.get("activity", "light"), ACTIVITY["light"])["factor"]
        goal = GOALS.get(body.get("goal", "keep"), GOALS["keep"])["factor"]
        kcal = bmr * activity * goal
        protein = weight * PROTEIN_PER_KG
        fat = kcal * FAT_SHARE / KCAL_PER_G["fat"]
        carbs = max(0.0, (kcal - protein * KCAL_PER_G["protein"] - fat * KCAL_PER_G["fat"]) / KCAL_PER_G["carbs"])
        result = {"kcal": kcal, "protein": protein, "fat": fat, "carbs": carbs,
                  "fiber": kcal / 1000 * FIBER_PER_1000_KCAL}
    for key, value in (override or {}).items():
        if key in result and value:
            result[key] = float(value)
    return {key: round(value) for key, value in result.items()}


def water_goal(body: dict, fallback: int) -> int:
    weight = body.get("weight")
    return int(round(weight * WATER_ML_PER_KG, -1)) if weight else fallback
