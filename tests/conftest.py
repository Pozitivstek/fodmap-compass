"""Общие фикстуры: каталог, временная БД, подменённый Open Food Facts, ASGI-клиент."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.api import create_app
from app.api.deps import AppContext
from app.config import Settings
from app.db import connect
from app.services.catalog import Catalog
from app.services.foodview import FoodResolver
from app.services.off import OpenFoodFacts
from app.storage import Storage

ROOT = Path(__file__).resolve().parent.parent
BOT_TOKEN = "123456:TEST-TOKEN"
DEV_USER = 42

OFF_PRODUCTS = {
    "4600000000017": {
        "code": "4600000000017", "product_name_ru": "Йогурт клубничный", "brands": "Тестовая ферма",
        "ingredients_text_ru": "молоко нормализованное, сахар, клубника, пектин",
        "allergens_tags": ["en:milk"],
        "nutriments": {"energy-kcal_100g": 85, "proteins_100g": 3, "fat_100g": 2.5, "carbohydrates_100g": 12},
    },
    "4600000000024": {
        "code": "4600000000024", "product_name": "Чипсы со вкусом чеснока",
        "ingredients_text": "картофель, масло подсолнечное, соль, чеснок сушёный, лук",
        "nutriments": {"energy_100g": 2200, "proteins_100g": 6, "fat_100g": 33, "carbohydrates_100g": 52},
    },
    "4600000000055": {
        "code": "4600000000055", "product_name": "Загадочный батончик", "nutriments": [1, 2],
        "serving_quantity": "inf", "image_front_small_url": "javascript:alert(1)",
    },
    "4600000000031": {
        "code": "4600000000031", "product_name_ru": "Молоко Деревенское 2,5%", "brands": "Пример",
        "nutriments": {"energy-kcal_100g": 52},
    },
}


def off_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "/api/v2/product/" in url:
        code = url.split("/product/")[1].split(".json")[0]
        product = OFF_PRODUCTS.get(code)
        if code == "4600000000048":  # сломанный ответ OFF
            return httpx.Response(200, text="<html>oops</html>")
        if not product:  # настоящий OFF отвечает 404 на неизвестный штрихкод
            return httpx.Response(404, json={"status": 0, "status_verbose": "product not found"})
        return httpx.Response(200, json={"status": 1, "product": product})
    if "search.openfoodfacts.org" in url:
        query = request.url.params.get("q", "").lower()
        hits = [p for p in OFF_PRODUCTS.values()
                if query in (p.get("product_name_ru") or p.get("product_name") or "").lower()]
        return httpx.Response(200, json={"hits": hits})
    return httpx.Response(404, json={})


def make_settings(tmp_path: Path, dev_mode: bool = True) -> Settings:
    return Settings(bot_token=BOT_TOKEN, webapp_url="https://example.test/", db_path=tmp_path / "test.db",
                    data_dir=ROOT / "data", webapp_dir=ROOT / "webapp", host="127.0.0.1", port=0,
                    dev_mode=dev_mode, dev_user_id=DEV_USER, init_data_ttl=3600, off_user_agent="tests",
                    reminders_enabled=False)


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.from_dir(ROOT / "data")


@pytest.fixture
async def storage(tmp_path):
    conn = await connect(tmp_path / "test.db")
    yield Storage.create(conn)
    await conn.close()


@pytest.fixture
async def ctx(tmp_path, storage, catalog) -> AppContext:
    client = httpx.AsyncClient(transport=httpx.MockTransport(off_handler))
    off = OpenFoodFacts(storage.extras, "tests", client=client)
    context = AppContext(settings=make_settings(tmp_path), storage=storage, catalog=catalog, off=off,
                         resolver=FoodResolver(catalog, off, storage.extras))
    yield context
    await client.aclose()


@pytest.fixture
async def client(ctx):
    app = create_app(ctx)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http


@pytest.fixture
async def onboarded(client):
    response = await client.put("/api/me", json={"conditions": ["fodmap", "lactose"], "onboarded": True,
                                                  "tz": "Europe/Moscow"})
    assert response.status_code == 200, response.text
    return client


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False)
