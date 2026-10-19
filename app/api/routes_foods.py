"""Продукты: поиск по каталогу и Open Food Facts, штрихкоды, карточка, личная отметка."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.api.deps import AppContext, current_user, get_ctx, limit
from app.api.schemas import CustomFoodIn, ToleranceIn, check_ref
from app.domain import CATEGORIES
from app.services import fodmap
from app.services.barcode import MAX_IMAGE_BYTES, BarcodeError, decode_async
from app.services.catalog import Food
from app.services.foodview import brief, card, custom_to_food, to_tolerance
from app.services.off import is_barcode, to_food
from app.services.tolerance import set_manual
from app.storage.users import User

router = APIRouter(prefix="/api/foods", tags=["foods"])
MIN_LOCAL_RESULTS = 5


async def guard_external(ctx: AppContext, user: User, ref: str) -> None:
    """Каждый промах кеша — запрос в Open Food Facts, поэтому такие запросы лимитируем."""
    kind, _, code = ref.partition(":")
    if kind == "off" and not await ctx.off.is_cached(code) and not ctx.limiters["external"].allow(f"external:{user.id}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком часто. Подождите немного.")


async def _briefs(ctx: AppContext, user: User, foods: list[Food]) -> list[dict]:
    profile = fodmap.Profile.from_settings(user.data)
    tolerances = await ctx.storage.tolerances.all(user.id)
    return [brief(f, fodmap.evaluate(f, profile, tolerance=to_tolerance(tolerances.get(f.ref)))) for f in foods]


async def _card(ctx: AppContext, user: User, food: Food) -> dict:
    profile = fodmap.Profile.from_settings(user.data)
    tolerances = await ctx.storage.tolerances.all(user.id)
    record = tolerances.get(food.ref)
    verdict = fodmap.evaluate(food, profile, tolerance=to_tolerance(record))
    payload = card(food, verdict, record, ctx.catalog, profile, tolerances)
    history = await ctx.storage.reactions.for_ref(user.id, food.ref, limit=10)
    return {**payload, "history": [r.to_dict() for r in history]}


@router.get("/categories")
async def categories(ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    counts = {code: len(ctx.catalog.by_category(code)) for code in CATEGORIES}
    return [{"code": code, **spec, "count": counts[code]} for code, spec in CATEGORIES.items() if counts[code]]


@router.get("/search")
async def search(q: str = Query(default="", max_length=80), category: str | None = None,
                 external: bool = True, user: User = Depends(current_user),
                 ctx: AppContext = Depends(get_ctx)) -> dict:
    query = q.strip()
    if category:
        local = ctx.catalog.by_category(category)
        if query:
            matched = {f.id for f in ctx.catalog.search(query, limit=200)}
            local = [f for f in local if f.id in matched]
    else:
        local = ctx.catalog.search(query) if query else []
    customs = [custom_to_food(c) for c in await ctx.storage.extras.custom_foods(user.id)
               if query and query.lower() in c["name"].lower()]
    products: list[Food] = []
    external_error = None
    wants_external = external and not category and len(query) >= 3 and len(local) < MIN_LOCAL_RESULTS
    if wants_external and ctx.limiters["external"].allow(f"external:{user.id}"):
        try:
            products = [to_food(hit, ctx.catalog) for hit in await ctx.off.search(query)]
        except RuntimeError:
            external_error = "Open Food Facts сейчас не отвечает — показаны только продукты из базы"
    return {"query": query, "catalog": await _briefs(ctx, user, [*customs, *local]),
            "products": await _briefs(ctx, user, products), "external_error": external_error}


@router.get("/item")
async def item(ref: str = Query(max_length=60), user: User = Depends(current_user),
               ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        check_ref(ref)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await guard_external(ctx, user, ref)
    try:
        food = await ctx.resolver.resolve(ref, user.id)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Open Food Facts сейчас не отвечает") from exc
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Продукт не найден")
    return await _card(ctx, user, food)


async def _by_barcode(ctx: AppContext, user: User, code: str) -> dict:
    if not is_barcode(code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Штрихкод — это 8–14 цифр")
    try:
        product = await ctx.off.product(code)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Open Food Facts сейчас не отвечает") from exc
    if not product:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Товар {code} пока не внесён в Open Food Facts")
    await ctx.storage.users.bump_stat(user, "scans")
    return await _card(ctx, user, to_food(product, ctx.catalog))


@router.get("/barcode/{code}")
async def barcode(code: str, user: User = Depends(limit("external")), ctx: AppContext = Depends(get_ctx)) -> dict:
    return await _by_barcode(ctx, user, code.strip())


@router.post("/barcode/photo")
async def barcode_photo(photo: UploadFile = File(...), user: User = Depends(limit("external")),
                        ctx: AppContext = Depends(get_ctx)) -> dict:
    data = await photo.read(MAX_IMAGE_BYTES + 1)
    try:
        code = await decode_async(data)
    except BarcodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if not code:
        raise HTTPException(422,
                            "Штрихкод не распознан. Сфотографируйте ближе и ровнее или введите цифры вручную")
    return await _by_barcode(ctx, user, code)


@router.get("/recent")
async def recent(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    entries = await ctx.storage.diary.recent(user.id)
    return [{"ref": e.ref, "name": e.name, "emoji": e.emoji, "grams": e.grams} for e in entries]


@router.post("/custom")
async def create_custom(body: CustomFoodIn, user: User = Depends(limit("write")),
                        ctx: AppContext = Depends(get_ctx)) -> dict:
    food_id = await ctx.storage.extras.add_custom_food(user.id, body.model_dump())
    data = await ctx.storage.extras.custom_food(user.id, food_id)
    return await _card(ctx, user, custom_to_food(data))


@router.delete("/custom/{food_id}")
async def delete_custom(food_id: int, user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> dict:
    if not await ctx.storage.extras.delete_custom_food(user.id, food_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Продукт не найден")
    return {"deleted": True}


@router.get("/tolerances")
async def tolerances(user: User = Depends(current_user), ctx: AppContext = Depends(get_ctx)) -> list[dict]:
    return [record.to_dict() for record in (await ctx.storage.tolerances.all(user.id)).values()]


@router.put("/tolerance")
async def set_tolerance(body: ToleranceIn, ref: str = Query(max_length=60), user: User = Depends(limit("write")),
                        ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        check_ref(ref)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    existing = await ctx.storage.tolerances.get(user.id, ref)
    record = set_manual(existing, ref, body.name, body.status, body.tested_g, body.note)
    await ctx.storage.tolerances.save(user.id, record)
    return record.to_dict()


@router.delete("/tolerance")
async def reset_tolerance(ref: str = Query(max_length=60), user: User = Depends(current_user),
                          ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"deleted": await ctx.storage.tolerances.delete(user.id, ref)}
