"""Рецепты: список с оценкой под человека, запись в дневник, ингредиенты в список покупок."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AppContext, current_user, get_ctx, limit
from app.api.schemas import RecipeLogIn
from app.services import fodmap
from app.services.catalog import normalize
from app.services.journal import add_entry, day_summary
from app.services.suggest import recipe_view
from app.storage.users import User

router = APIRouter(prefix="/api/recipes", tags=["recipes"])
LEVEL_RANK = {fodmap.GREEN: 0, fodmap.YELLOW: 1, fodmap.GREY: 2, fodmap.RED: 3}


async def _views(ctx: AppContext, user: User) -> list[dict]:
    profile = fodmap.Profile.from_settings(user.data)
    tolerances = await ctx.storage.tolerances.all(user.id)
    return [recipe_view(r, ctx.catalog, profile, tolerances) for r in ctx.catalog.recipes.values()]


def _matches(view: dict, query: str) -> bool:
    text = normalize(" ".join([view["title"], view["description"], *view["tags"],
                               *(i["name"] for i in view["ingredients"])]))
    return all(word in text for word in normalize(query).split())


@router.get("")
async def recipes(meal: str | None = None, q: str = Query(default="", max_length=80), safe_only: bool = False,
                  user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    views = await _views(ctx, user)
    views = [v for v in views if (not meal or meal in v["meals"]) and (not q or _matches(v, q))
             and (not safe_only or v["level"] in (fodmap.GREEN, fodmap.YELLOW))]
    views.sort(key=lambda v: (LEVEL_RANK[v["level"]], v["minutes"]))
    return [{k: v[k] for k in ("id", "title", "emoji", "meals", "minutes", "servings", "description", "tags",
                               "per_serving", "level", "title_level", "problems")} for v in views]


def _recipe_or_404(ctx: AppContext, recipe_id: str):
    recipe = ctx.catalog.recipe(recipe_id)
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Рецепт не найден")
    return recipe


@router.get("/{recipe_id}")
async def recipe(recipe_id: str, user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> dict:
    found = _recipe_or_404(ctx, recipe_id)
    profile = fodmap.Profile.from_settings(user.data)
    view = recipe_view(found, ctx.catalog, profile, await ctx.storage.tolerances.all(user.id))
    view["search_url"] = "https://yandex.ru/search/?text=" + "+".join(f"low FODMAP рецепт {found.title}".split())
    return view


@router.post("/{recipe_id}/log")
async def log_recipe(recipe_id: str, body: RecipeLogIn, user: User = Depends(limit("write")),
                     ctx: AppContext = Depends(get_ctx)) -> dict:
    found = _recipe_or_404(ctx, recipe_id)
    day = body.day.isoformat()
    factor = body.servings / found.servings
    for ing in found.ingredients:
        food = ctx.catalog.food(ing.food_id)
        grams = round(ing.grams * factor, 1)
        if grams >= 1:
            await add_entry(ctx.storage, user, food, day, body.meal, grams)
    updated = await ctx.storage.users.bump_stat(user, "recipes_logged")
    return await day_summary(ctx.storage, updated, day)


@router.post("/{recipe_id}/shopping")
async def to_shopping(recipe_id: str, user: User = Depends(limit("write")), ctx: AppContext = Depends(get_ctx)) -> dict:
    found = _recipe_or_404(ctx, recipe_id)
    items = []
    for ing in found.ingredients:
        food = ctx.catalog.food(ing.food_id)
        if food.category != "spice":
            items.append((f"{food.name} — {ing.grams:g} г", food.ref))
    await ctx.storage.extras.add_shopping(user.id, items)
    return {"items": await ctx.storage.extras.shopping(user.id)}
