"""Дневник: записи еды и самочувствия, календарь."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import AppContext, current_user, get_ctx, limit
from app.api.routes_foods import guard_external
from app.api.schemas import EntryIn, EntryPatch, ReactionIn
from app.services.insights import reaction_score
from app.services.journal import add_entry, day_summary, record_reaction, today_for, update_entry
from app.storage.users import User

router = APIRouter(prefix="/api", tags=["diary"])
MAX_FUTURE_DAYS = 1


def _check_day(day: date, user: User) -> str:
    today = date.fromisoformat(today_for(user))
    if day > today + timedelta(days=MAX_FUTURE_DAYS):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нельзя записывать на будущее")
    return day.isoformat()


@router.get("/diary")
async def diary(day: date | None = None, user: User = Depends(current_user),
                ctx: AppContext = Depends(get_ctx)) -> dict:
    return await day_summary(ctx.storage, user, (day.isoformat() if day else today_for(user)))


@router.post("/diary")
async def create_entry(body: EntryIn, user: User = Depends(limit("write")), ctx: AppContext = Depends(get_ctx)) -> dict:
    day = _check_day(body.day, user)
    await guard_external(ctx, user, body.ref)
    try:
        food = await ctx.resolver.resolve(body.ref, user.id)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Open Food Facts сейчас не отвечает") from exc
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Продукт не найден")
    entry_id = await add_entry(ctx.storage, user, food, day, body.meal, body.grams)
    return {"id": entry_id, "summary": await day_summary(ctx.storage, user, day)}


@router.patch("/diary/{entry_id}")
async def patch_entry(entry_id: int, body: EntryPatch, user: User = Depends(limit("write")),
                      ctx: AppContext = Depends(get_ctx)) -> dict:
    entry = await ctx.storage.diary.get(user.id, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена")
    await update_entry(ctx.storage, user, entry, body.grams or entry.grams, body.meal or entry.meal)
    return await day_summary(ctx.storage, user, entry.day)


@router.delete("/diary/{entry_id}")
async def delete_entry(entry_id: int, user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> dict:
    entry = await ctx.storage.diary.get(user.id, entry_id)
    if entry is None or not await ctx.storage.diary.delete(user.id, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена")
    return await day_summary(ctx.storage, user, entry.day)


@router.post("/reactions")
async def create_reaction(body: ReactionIn, user: User = Depends(limit("write")),
                          ctx: AppContext = Depends(get_ctx)) -> dict:
    day = _check_day(body.day, user)
    name = ""
    if body.ref:
        food = await ctx.resolver.resolve(body.ref, user.id)
        name = food.name if food else ""
    result = await record_reaction(ctx.storage, user, day=day, meal=body.meal, ref=body.ref, feeling=body.feeling,
                                   symptoms=body.symptoms, severity=body.severity, note=body.note.strip(),
                                   ref_name=name, grams=body.grams)
    return {**result, "summary": await day_summary(ctx.storage, user, day)}


@router.delete("/reactions/{reaction_id}")
async def delete_reaction(reaction_id: int, user: User = Depends(current_user),
                          ctx: AppContext = Depends(get_ctx)) -> dict:
    if not await ctx.storage.reactions.delete(user.id, reaction_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Запись не найдена")
    return {"deleted": True}


@router.get("/calendar")
async def calendar(month: str = Query(pattern=r"^\d{4}-\d{2}$"), user: User = Depends(current_user),
                   ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError as exc:
        raise HTTPException(422, "Месяц в формате ГГГГ-ММ") from exc
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    entries = await ctx.storage.diary.between(user.id, start.isoformat(), end.isoformat())
    reactions = await ctx.storage.reactions.between(user.id, start.isoformat(), end.isoformat())
    days: dict[str, dict] = {}
    for entry in entries:
        days.setdefault(entry.day, {"entries": 0, "kcal": 0.0, "score": None})
        days[entry.day]["entries"] += 1
        days[entry.day]["kcal"] += entry.macros.get("kcal", 0)
    for reaction in reactions:
        slot = days.setdefault(reaction.day, {"entries": 0, "kcal": 0.0, "score": None})
        slot["score"] = max(slot["score"] or 0, reaction_score(reaction))
    return {"month": month, "days": days}
