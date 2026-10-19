"""Вода и список покупок."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AppContext, current_user, get_ctx, limit
from app.api.schemas import ShoppingIn, ShoppingPatch, WaterIn
from app.services.journal import today_for
from app.storage.users import User

router = APIRouter(prefix="/api", tags=["misc"])


@router.post("/water")
async def water(body: WaterIn, user: User = Depends(limit("write")), ctx: AppContext = Depends(get_ctx)) -> dict:
    day = body.day.isoformat() if body.day else today_for(user)
    ml = await ctx.storage.extras.add_water(user.id, day, body.delta_ml)
    return {"day": day, "ml": ml, "goal": int(user.setting("water_goal_ml") or 2000)}


@router.get("/shopping")
async def shopping(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return await ctx.storage.extras.shopping(user.id)


@router.post("/shopping")
async def add_shopping(body: ShoppingIn, user: User = Depends(limit("write")),
                       ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    await ctx.storage.extras.add_shopping(user.id, [(name, "") for name in body.names])
    return await ctx.storage.extras.shopping(user.id)


@router.patch("/shopping/{item_id}")
async def toggle_shopping(item_id: int, body: ShoppingPatch, user: User = Depends(current_user),
                          ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    if not await ctx.storage.extras.set_shopping_done(user.id, item_id, body.done):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нет такого пункта")
    return await ctx.storage.extras.shopping(user.id)


@router.delete("/shopping/{item_id}")
async def delete_shopping(item_id: int, user: User = Depends(current_user),
                          ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    await ctx.storage.extras.delete_shopping(user.id, item_id)
    return await ctx.storage.extras.shopping(user.id)


@router.delete("/shopping")
async def clear_done(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    await ctx.storage.extras.delete_shopping(user.id)
    return await ctx.storage.extras.shopping(user.id)
