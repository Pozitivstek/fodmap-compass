"""Рецепты с оценкой под человека и подсказки «что съесть сейчас»."""

from __future__ import annotations

import random

from app.services import fodmap
from app.services.catalog import Catalog, Recipe
from app.services.foodview import brief, to_tolerance
from app.services.nutrition import macros, total
from app.storage.reactions import ToleranceRecord

MEAL_BY_HOUR = ((5, "snack"), (11, "breakfast"), (16, "lunch"), (21, "dinner"))
SNACK_CATEGORIES = ("fruit", "nut", "sweet", "dairy", "alt", "grain")
SUGGESTED_RECIPES = 4
SUGGESTED_SNACKS = 6


def meal_for_hour(hour: int) -> str:
    for limit, meal in MEAL_BY_HOUR:
        if hour < limit:
            return meal
    return "snack"


def recipe_view(recipe: Recipe, catalog: Catalog, profile: fodmap.Profile,
                tolerances: dict[str, ToleranceRecord]) -> dict:
    ingredients, loads, levels, nutrition, problems = [], [], [], [], []
    for ing in recipe.ingredients:
        food = catalog.food(ing.food_id)
        per_serving = ing.grams / recipe.servings
        verdict = fodmap.evaluate(food, profile, per_serving, to_tolerance(tolerances.get(food.ref)))
        loads.append(verdict.loads)
        levels.append(verdict.level)
        nutrition.append(macros(food, per_serving))
        if verdict.level in (fodmap.RED, fodmap.GREY):
            problems.append(food.name)
        ingredients.append({"ref": food.ref, "name": food.name, "emoji": food.emoji, "grams": ing.grams,
                            "note": ing.note, "level": verdict.level, "reasons": list(verdict.reasons),
                            "swaps": [catalog.food(s).name for s in food.swaps if catalog.food(s)]})
    stacked = fodmap.stack(loads)
    level = fodmap.worst([*levels, stacked["level"]])
    return {
        "id": recipe.id, "title": recipe.title, "emoji": recipe.emoji, "meals": list(recipe.meals),
        "minutes": recipe.minutes, "servings": recipe.servings, "description": recipe.description,
        "tags": list(recipe.tags), "per_serving": total(nutrition), "level": level,
        "title_level": fodmap.LEVEL_TITLES[level], "stack": stacked, "problems": problems,
        "ingredients": ingredients, "steps": list(recipe.steps),
    }


def _recipe_score(view: dict, likes: tuple[str, ...], remaining_kcal: float | None) -> float:
    score = {fodmap.GREEN: 3.0, fodmap.YELLOW: 1.0}.get(view["level"], -10.0)
    names = " ".join(i["name"].lower() for i in view["ingredients"])
    score += sum(0.7 for like in likes if like and like in names)
    if remaining_kcal is not None and view["per_serving"]["kcal"] > remaining_kcal * 1.2:
        score -= 1.5
    return score


def suggestions(catalog: Catalog, profile: fodmap.Profile, tolerances: dict[str, ToleranceRecord],
                meal: str, likes: tuple[str, ...], remaining_kcal: float | None, seed: str) -> dict:
    rng = random.Random(seed)
    views = [recipe_view(r, catalog, profile, tolerances) for r in catalog.recipes.values() if meal in r.meals]
    rng.shuffle(views)
    ranked = sorted((v for v in views if v["level"] in (fodmap.GREEN, fodmap.YELLOW)),
                    key=lambda v: -_recipe_score(v, likes, remaining_kcal))
    snacks = []
    personal_ok = {ref for ref, rec in tolerances.items() if rec.status == "ok"}
    candidates = [f for f in catalog.foods.values() if f.category in SNACK_CATEGORIES]
    rng.shuffle(candidates)
    candidates.sort(key=lambda f: f.ref not in personal_ok)
    for food in candidates:
        verdict = fodmap.evaluate(food, profile, tolerance=to_tolerance(tolerances.get(food.ref)))
        if verdict.level == fodmap.GREEN and not verdict.disliked:
            snacks.append(brief(food, verdict))
        if len(snacks) >= SUGGESTED_SNACKS:
            break
    return {"meal": meal, "recipes": ranked[:SUGGESTED_RECIPES], "snacks": snacks}
