"""Регрессии по итогам ревью: OFF, идемпотентность, авторизация, профиль."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api.auth import InitDataError, validate
from app.bot.handlers import build_router
from app.services.journal import add_entry
from tests.conftest import BOT_TOKEN


async def _today(client) -> str:
    return (await client.get("/api/home")).json()["day"]


async def test_unknown_barcode_is_404_and_cached(ctx, onboarded):
    assert (await onboarded.get("/api/foods/barcode/4600000009999")).status_code == 404
    assert await ctx.off.is_cached("4600000009999")


async def test_broken_off_payload_is_503_not_500(onboarded):
    assert (await onboarded.get("/api/foods/barcode/4600000000048")).status_code == 503


async def test_product_without_ingredients_is_not_green(onboarded):
    card = (await onboarded.get("/api/foods/barcode/4600000000055")).json()
    assert card["unknown"] and card["verdict"]["level"] == "yellow"
    assert card["portion"]["grams"] == 100 and card["image"] == ""
    assert card["per100"]["kcal"] == 0


async def test_search_hits_are_not_cached_as_full_products(ctx, onboarded):
    await onboarded.get("/api/foods/search", params={"q": "йогурт клубничный"})
    assert not await ctx.off.is_cached("4600000000017")


def test_non_ascii_hash_is_rejected_cleanly():
    try:
        validate("auth_date=1&hash=%C3%A9", BOT_TOKEN, 3600)
    except InitDataError as exc:
        assert "подпись" in str(exc)
    else:
        raise AssertionError("expected InitDataError")


async def test_calendar_rejects_bad_month(onboarded):
    assert (await onboarded.get("/api/calendar", params={"month": "2024-13"})).status_code == 422


async def test_double_tap_reaction_counts_once(onboarded):
    day = await _today(onboarded)
    body = {"day": day, "ref": "cat:kiwi", "feeling": "bad", "grams": 75}
    first = (await onboarded.post("/api/reactions", json=body)).json()
    second = (await onboarded.post("/api/reactions", json=body)).json()
    assert second["duplicate"] and second["id"] == first["id"]
    card = (await onboarded.get("/api/foods/item", params={"ref": "cat:kiwi"})).json()
    assert card["tolerance"]["bad_count"] == 1


async def test_profile_fields_can_be_cleared(onboarded):
    await onboarded.put("/api/me", json={"body": {"weight": 70, "height": 170}})
    me = (await onboarded.put("/api/me", json={"body": {"weight": None}})).json()
    assert me["settings"]["body"]["weight"] is None and me["settings"]["body"]["height"] == 170


async def test_stale_snapshot_does_not_revert_profile(ctx, onboarded):
    stale = await ctx.storage.users.get(42)
    await onboarded.put("/api/me", json={"conditions": ["celiac"]})
    await ctx.storage.users.bump_stat(stale, "scans")
    fresh = await ctx.storage.users.get(42)
    assert fresh.setting("conditions") == ["celiac"] and fresh.setting("stats")["scans"] == 1


async def test_patch_updates_fodmap_loads(ctx, onboarded):
    day = await _today(onboarded)
    entry_id = (await onboarded.post("/api/diary", json={"ref": "cat:avocado", "day": day, "meal": "lunch",
                                                        "grams": 30})).json()["id"]
    await onboarded.patch(f"/api/diary/{entry_id}", json={"grams": 90})
    entry = await ctx.storage.diary.get(42, entry_id)
    assert entry.food["loads"]["sor"] == 3.0


async def test_water_accepts_large_steps(onboarded):
    assert (await onboarded.post("/api/water", json={"delta_ml": 2750})).json()["ml"] == 2750


async def test_answered_prompt_is_not_recorded_twice(ctx):
    user = await ctx.storage.users.ensure(77, "Аня", "anya")
    user = await ctx.storage.users.update(user, {"conditions": ["fodmap"]}, tz="Europe/Moscow", onboarded=True)
    day = datetime.now(timezone(timedelta(hours=3))).date().isoformat()
    await add_entry(ctx.storage, user, ctx.catalog.food("apple"), day, "snack", 150)
    prompt = (await ctx.storage.extras.due_prompts(datetime.now(timezone.utc) + timedelta(days=1)))[0]
    handler = next(h.callback for h in build_router(ctx).callback_query.handlers if h.callback.__name__ == "reaction")
    for _ in range(2):
        call = SimpleNamespace(data=f"rx:{prompt['id']}:bad", from_user=SimpleNamespace(id=77, first_name="Аня",
                               username="anya"), answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock()))
        await handler(call)
    call.answer.assert_awaited_with("Уже записано — спасибо!")
    assert (await ctx.storage.tolerances.get(77, "cat:apple")).bad_count == 1
