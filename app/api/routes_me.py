"""Профиль, справочники и главный экран."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends

from app.api.deps import AppContext, current_user, get_ctx, limit
from app.api.schemas import THEMES, ProfileIn
from app.clock import local_now
from app.domain import (ACTIVITY, ALLERGENS, CATEGORIES, CONDITIONS, DIET_STYLES, FEELINGS, FODMAP_GROUPS, GOALS,
                        MEALS, SYMPTOMS, TIPS, TOLERANCE_STATUSES)
from app.services import fodmap, nutrition
from app.services.journal import day_summary, stats, today_for
from app.services.suggest import meal_for_hour, suggestions
from app.storage.users import User

router = APIRouter(prefix="/api", tags=["me"])


def user_payload(user: User) -> dict:
    body = user.setting("body") or {}
    return {
        "id": user.id, "first_name": user.first_name, "username": user.username, "tz": user.tz,
        "onboarded": user.onboarded,
        "settings": {key: user.setting(key) for key in (
            "conditions", "diet_style", "dislikes", "likes", "tolerated_groups", "body", "targets_override",
            "water_goal_ml", "theme", "reminders", "seen_achievements")},
        "targets": nutrition.targets(body, user.setting("targets_override")),
        "suggested_water_ml": nutrition.water_goal(body, 2000),
    }


@router.get("/meta")
async def meta() -> dict:
    return {"conditions": CONDITIONS, "groups": FODMAP_GROUPS, "allergens": ALLERGENS, "categories": CATEGORIES,
            "diet_styles": DIET_STYLES, "meals": MEALS, "symptoms": SYMPTOMS, "feelings": FEELINGS,
            "activity": ACTIVITY, "goals": GOALS, "tolerance": TOLERANCE_STATUSES, "themes": list(THEMES)}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return user_payload(user)


@router.put("/me")
async def update_me(body: ProfileIn, user: User = Depends(limit("write")),
                    ctx: AppContext = Depends(get_ctx)) -> dict:
    patch = body.model_dump(exclude_none=True, exclude={"tz", "onboarded", "body", "targets_override"})
    # В теле и нормах явный null означает «стереть значение», поэтому берём только присланные поля.
    for key in ("body", "targets_override"):
        nested = getattr(body, key)
        if nested is not None:
            patch[key] = nested.model_dump(exclude_unset=True)
    updated = await ctx.storage.users.update(user, patch, tz=body.tz, onboarded=body.onboarded)
    return user_payload(updated)


@router.delete("/me")
async def delete_me(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> dict:
    await ctx.storage.users.delete(user.id)
    return {"deleted": True}


def _tip(user_id: int, day: str) -> str:
    digest = hashlib.sha256(f"{user_id}:{day}".encode()).digest()
    return TIPS[digest[0] % len(TIPS)]


@router.get("/home")
async def home(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> dict:
    day = today_for(user)
    summary = await day_summary(ctx.storage, user, day)
    progress = await stats(ctx.storage, user)
    seen = set(user.setting("seen_achievements") or [])
    fresh = [a for a in progress["achievements"] if a["earned"] and a["code"] not in seen]
    remaining = summary["targets"]["kcal"] - summary["totals"]["kcal"]
    meal = meal_for_hour(local_now(user.tz).hour)
    profile = fodmap.Profile.from_settings(user.data)
    tolerances = await ctx.storage.tolerances.all(user.id)
    ideas = suggestions(ctx.catalog, profile, tolerances, meal, tuple(user.setting("likes") or ()),
                        remaining if remaining > 0 else None, seed=f"{user.id}:{day}:{meal}")
    pending = [code for code, m in summary["meals"].items() if m["entries"] and not m["reactions"]]
    return {"day": day, "user": {"first_name": user.first_name}, "streak": progress["streak"], "week": progress["week"],
            "summary": summary, "suggestions": ideas, "achievements": progress["achievements"],
            "new_achievements": fresh, "pending_reactions": pending, "tip": _tip(user.id, day)}
