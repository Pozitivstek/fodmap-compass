"""API целиком: онбординг, поиск, дневник, реакции, рецепты, аналитика, отчёт, вода, покупки."""

import json
import time
from urllib.parse import urlencode

import pytest

from app.api.auth import sign
from tests.conftest import BOT_TOKEN, DEV_USER



async def _today(client) -> str:
    return (await client.get("/api/home")).json()["day"]


async def test_health_meta_and_static(client):
    assert (await client.get("/api/health")).json()["foods"] >= 300
    meta = (await client.get("/api/meta")).json()
    assert "fodmap" in meta["conditions"] and "mint" in meta["themes"]
    page = await client.get("/")
    assert "ФудКомпас" in page.text
    assert (await client.get("/css/app.css")).status_code == 200


async def test_profile_update_and_validation(client):
    me = (await client.get("/api/me")).json()
    assert me["id"] == DEV_USER and not me["onboarded"]
    body = {"conditions": ["fodmap"], "diet_style": "vegetarian", "dislikes": [" Грибы ", "грибы"],
            "body": {"sex": "male", "birth_year": 1990, "height": 180, "weight": 80}, "theme": "ocean",
            "tz": "Asia/Yekaterinburg", "onboarded": True, "reminders": {"meals": {"lunch": "12:30"}}}
    me = (await client.put("/api/me", json=body)).json()
    assert me["onboarded"] and me["tz"] == "Asia/Yekaterinburg"
    assert me["settings"]["dislikes"] == ["грибы"]
    assert me["settings"]["reminders"]["meals"]["lunch"] == "12:30"
    assert me["settings"]["reminders"]["meals"]["dinner"] == "19:00"
    assert me["targets"]["kcal"] > 2000
    for bad in ({"conditions": ["vampire"]}, {"tz": "Mars/Base"}, {"theme": "neon"},
                {"reminders": {"meals": {"lunch": "25:00"}}}):
        assert (await client.put("/api/me", json=bad)).status_code == 422


async def test_requires_signature_when_not_dev(ctx, client):
    from dataclasses import replace
    ctx.settings = replace(ctx.settings, dev_mode=False)
    assert (await client.get("/api/me")).status_code == 401
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 555, "first_name": "Тест"})}
    init = urlencode({**fields, "hash": sign(fields, BOT_TOKEN)})
    me = await client.get("/api/me", headers={"X-Telegram-Init-Data": init})
    assert me.json()["id"] == 555


async def test_search_catalog_and_products(onboarded):
    data = (await onboarded.get("/api/foods/search", params={"q": "авокадо"})).json()
    assert data["catalog"][0]["ref"] == "cat:avocado"
    shop = (await onboarded.get("/api/foods/search", params={"q": "чипсы со вкусом"})).json()
    assert shop["products"][0]["ref"] == "off:4600000000024"
    assert shop["products"][0]["verdict"]["level"] == "red"
    category = (await onboarded.get("/api/foods/search", params={"category": "spice", "q": "перец"})).json()
    assert all(item["category"] == "spice" for item in category["catalog"])
    cats = (await onboarded.get("/api/foods/categories")).json()
    assert {c["code"] for c in cats} >= {"veg", "fruit"}


async def test_food_card_and_barcodes(onboarded):
    card = (await onboarded.get("/api/foods/item", params={"ref": "cat:onion"})).json()
    assert card["verdict"]["level"] == "red"
    assert any(s["ref"] == "cat:garlic_oil" for s in card["swaps"])
    yogurt = (await onboarded.get("/api/foods/barcode/4600000000017")).json()
    assert yogurt["brand"] == "Тестовая ферма" and yogurt["verdict"]["level"] == "yellow"
    milk = (await onboarded.get("/api/foods/item", params={"ref": "off:4600000000031"})).json()
    assert "Молоко коровье" in milk["note"]
    assert (await onboarded.get("/api/foods/barcode/4600000009999")).status_code == 404
    assert (await onboarded.get("/api/foods/barcode/abc")).status_code == 400
    assert (await onboarded.get("/api/foods/item", params={"ref": "drop table"})).status_code == 400
    assert (await onboarded.get("/api/foods/item", params={"ref": "cat:unknown"})).status_code == 404


async def test_barcode_photo_errors(onboarded):
    files = {"photo": ("x.jpg", b"not an image", "image/jpeg")}
    assert (await onboarded.post("/api/foods/barcode/photo", files=files)).status_code == 400


async def test_diary_reaction_updates_personal_tolerance(onboarded):
    day = await _today(onboarded)
    created = await onboarded.post("/api/diary", json={"ref": "cat:avocado", "day": day, "meal": "lunch", "grams": 100})
    assert created.status_code == 200
    summary = created.json()["summary"]
    assert summary["meals"]["lunch"]["entries"][0]["verdict"]["level"] == "red"
    await onboarded.post("/api/diary", json={"ref": "cat:rice_white", "day": day, "meal": "lunch", "grams": 60})
    reaction = (await onboarded.post("/api/reactions", json={"day": day, "meal": "lunch", "feeling": "bad",
                                                              "symptoms": ["bloating"], "severity": 3})).json()
    assert [u["ref"] for u in reaction["updated"]] == ["cat:avocado"]
    card = (await onboarded.get("/api/foods/item", params={"ref": "cat:avocado"})).json()
    assert card["tolerance"]["status"] == "avoid" and card["history"]

    good = (await onboarded.post("/api/reactions", json={"day": day, "ref": "cat:rice_white", "feeling": "great",
                                                          "grams": 60})).json()
    assert good["updated"][0]["status"] == "ok"
    manual = await onboarded.put("/api/foods/tolerance", params={"ref": "cat:avocado"},
                                 json={"status": "ok", "tested_g": 50, "name": "Авокадо"})
    assert manual.json()["manual"]
    assert len((await onboarded.get("/api/foods/tolerances")).json()) == 2
    assert (await onboarded.delete("/api/foods/tolerance", params={"ref": "cat:avocado"})).json()["deleted"]


async def test_diary_edit_delete_and_validation(onboarded):
    day = await _today(onboarded)
    entry_id = (await onboarded.post("/api/diary", json={"ref": "cat:kiwi", "day": day, "meal": "snack",
                                                        "grams": 75})).json()["id"]
    patched = (await onboarded.patch(f"/api/diary/{entry_id}", json={"grams": 150, "meal": "breakfast"})).json()
    assert patched["meals"]["breakfast"]["entries"][0]["grams"] == 150
    assert (await onboarded.delete(f"/api/diary/{entry_id}")).status_code == 200
    assert (await onboarded.delete(f"/api/diary/{entry_id}")).status_code == 404
    assert (await onboarded.patch("/api/diary/9999", json={"grams": 1})).status_code == 404
    future = {"ref": "cat:kiwi", "day": "2999-01-01", "meal": "snack", "grams": 10}
    assert (await onboarded.post("/api/diary", json=future)).status_code == 400
    assert (await onboarded.post("/api/diary", json={**future, "day": day, "grams": -5})).status_code == 422
    assert (await onboarded.post("/api/diary", json={**future, "day": day, "ref": "cat:nope"})).status_code == 404
    recent = (await onboarded.get("/api/foods/recent")).json()
    assert recent == []


async def test_custom_food(onboarded):
    card = (await onboarded.post("/api/foods/custom", json={"name": "Бабушкины сырники", "kcal": 220,
                                                             "groups": ["lac"], "allergens": ["milk"]})).json()
    assert card["ref"].startswith("custom:") and card["source"] == "custom"
    found = (await onboarded.get("/api/foods/search", params={"q": "сырники"})).json()
    assert found["catalog"][0]["ref"] == card["ref"]
    food_id = card["ref"].split(":")[1]
    assert (await onboarded.delete(f"/api/foods/custom/{food_id}")).json()["deleted"]
    assert (await onboarded.delete(f"/api/foods/custom/{food_id}")).status_code == 404
    bad = await onboarded.post("/api/foods/custom", json={"name": "x", "groups": ["zzz"]})
    assert bad.status_code == 422


async def test_recipes_log_and_shopping(onboarded):
    items = (await onboarded.get("/api/recipes", params={"meal": "breakfast", "safe_only": True})).json()
    assert items and all("breakfast" in r["meals"] for r in items)
    assert (await onboarded.get("/api/recipes", params={"q": "плов"})).json()[0]["id"] == "plov_garlic_oil"
    recipe = (await onboarded.get("/api/recipes/oats_strawberry")).json()
    assert recipe["level"] == "green" and "yandex" in recipe["search_url"]
    day = await _today(onboarded)
    summary = (await onboarded.post("/api/recipes/oats_strawberry/log", json={"day": day, "meal": "breakfast",
                                                                              "servings": 1})).json()
    assert len(summary["meals"]["breakfast"]["entries"]) == 5
    shop = (await onboarded.post("/api/recipes/oats_strawberry/shopping")).json()["items"]
    assert any("Клубника" in i["name"] for i in shop)
    item_id = shop[0]["id"]
    assert (await onboarded.patch(f"/api/shopping/{item_id}", json={"done": True})).json()[-1]["done"]
    await onboarded.post("/api/shopping", json={"names": ["Безлактозный йогурт"]})
    left = (await onboarded.delete("/api/shopping")).json()
    assert all(not i["done"] for i in left)
    await onboarded.delete(f"/api/shopping/{left[0]['id']}")
    assert (await onboarded.patch("/api/shopping/99999", json={"done": True})).status_code == 404
    assert (await onboarded.get("/api/recipes/nope")).status_code == 404


async def test_home_water_calendar_insights_report(onboarded):
    day = await _today(onboarded)
    await onboarded.post("/api/diary", json={"ref": "cat:apple", "day": day, "meal": "snack", "grams": 150})
    await onboarded.post("/api/reactions", json={"day": day, "meal": "snack", "feeling": "mild"})
    water = (await onboarded.post("/api/water", json={"delta_ml": 250})).json()
    assert water["ml"] == 250
    home = (await onboarded.get("/api/home")).json()
    assert home["streak"]["current"] == 1 and len(home["week"]) == 7
    assert home["summary"]["water"]["ml"] == 250 and home["tip"]
    assert any(a["code"] == "first_entry" for a in home["new_achievements"])
    calendar = (await onboarded.get("/api/calendar", params={"month": day[:7]})).json()
    assert calendar["days"][day]["entries"] == 1
    data = (await onboarded.get("/api/insights", params={"days": 7})).json()
    assert data["logged_days"] == 1 and data["progress"]["values"]["entries"] == 1
    report = await onboarded.post("/api/report", json={"days": 7})
    if report.status_code == 500:
        pytest.skip("в системе нет шрифта с кириллицей")
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF")


async def test_report_sent_via_bot_and_rate_limited(ctx, onboarded):
    sent = []

    async def fake_send(chat_id, pdf, filename, caption):
        sent.append((chat_id, filename))

    ctx.send_document = fake_send
    first = await onboarded.post("/api/report", json={"days": 7})
    if first.status_code == 500:
        pytest.skip("в системе нет шрифта с кириллицей")
    assert first.json() == {"sent": True} and sent[0][0] == DEV_USER
    for _ in range(2):
        await onboarded.post("/api/report", json={"days": 7})
    assert (await onboarded.post("/api/report", json={"days": 7})).status_code == 429


async def test_delete_me(onboarded):
    assert (await onboarded.delete("/api/me")).json() == {"deleted": True}
    assert not (await onboarded.get("/api/me")).json()["onboarded"]
