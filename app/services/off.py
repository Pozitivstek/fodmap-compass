"""Open Food Facts: товары по штрихкоду и поиску, перевод в Food с оценкой FODMAP по составу."""

from __future__ import annotations

import html
import logging
import math
import re

import httpx

from app.services.catalog import Catalog, Food, Portion
from app.services.ingredients import analyze
from app.storage.extras import ExtrasRepo

log = logging.getLogger(__name__)

PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
SEARCH_URL = "https://search.openfoodfacts.org/search"
FIELDS = ("code,product_name,product_name_ru,generic_name_ru,brands,ingredients_text_ru,ingredients_text,"
          "allergens_tags,nutriments,image_front_small_url,quantity,serving_quantity")
BARCODE_RE = re.compile(r"^\d{6,14}$")
TIMEOUT = httpx.Timeout(8.0, connect=5.0)
DEFAULT_PORTION_G = 100.0
MAX_PORTION_G = 3000.0
UNKNOWN_NOTE = "Состав не указан в Open Food Facts — оценка невозможна, проверьте упаковку"


class OffUnavailable(RuntimeError):
    """Open Food Facts не ответил или ответил мусором."""


def is_barcode(code: str) -> bool:
    return bool(BARCODE_RE.match(code))


def _text(value) -> str:
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return html.unescape(str(value or "")).strip()


def _number(nutriments: dict, key: str) -> float:
    try:
        value = float(nutriments.get(f"{key}_100g"))
    except (TypeError, ValueError):
        return 0.0
    return round(value, 1) if math.isfinite(value) and value >= 0 else 0.0


def _kcal(nutriments: dict) -> float:
    kcal = _number(nutriments, "energy-kcal")
    if kcal:
        return kcal
    kj = _number(nutriments, "energy")
    return round(kj / 4.184, 1) if kj else 0.0


def _portion(value) -> float:
    try:
        grams = float(value)
    except (TypeError, ValueError):
        return DEFAULT_PORTION_G
    return grams if math.isfinite(grams) and 0 < grams <= MAX_PORTION_G else DEFAULT_PORTION_G


def _json(response: httpx.Response) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        raise OffUnavailable("ответ не JSON") from exc
    if not isinstance(payload, dict):
        raise OffUnavailable("неожиданный формат ответа")
    return payload


def has_ingredients(product: dict) -> bool:
    return bool(_text(product.get("ingredients_text_ru") or product.get("ingredients_text")))


def to_food(product: dict, catalog: Catalog) -> Food:
    code = _text(product.get("code"))
    name = _text(product.get("product_name_ru") or product.get("product_name") or product.get("generic_name_ru"))
    name = name or f"Товар {code}"
    brand = _text(product.get("brands"))
    ingredients = _text(product.get("ingredients_text_ru") or product.get("ingredients_text"))
    nutriments = product.get("nutriments") if isinstance(product.get("nutriments"), dict) else {}
    allergen_tags = product.get("allergens_tags") if isinstance(product.get("allergens_tags"), list) else []
    analysis = analyze(ingredients, allergen_tags, name=name)
    groups = tuple(analysis.groups)
    low_g: float | None = None if analysis.strong else DEFAULT_PORTION_G
    note = ("Оценка по составу упаковки: " + ", ".join(analysis.matches[:6])) if analysis.matches else ""
    # Состава нет — узнаём базовый продукт по названию («Молоко Домик в деревне 2,5%» → молоко).
    base = None if ingredients else catalog.best_name_match(name)
    allergens, tags = set(analysis.allergens), set(analysis.tags)
    high_g = None
    if base is not None:
        groups, low_g, high_g = base.groups, base.low_g, base.high_g
        allergens |= set(base.allergens)
        tags |= set(base.tags)
        note = f"Состава нет — оценка по похожему продукту «{base.name}»"
    unknown = not ingredients and base is None
    if unknown:
        note = UNKNOWN_NOTE
    if analysis.lactose_free:
        tags.add("lactose_free")
    return Food(
        id=f"off_{code}", name=name, aliases=(), en=(), category="product", emoji="🛒",
        kcal=_kcal(nutriments), protein=_number(nutriments, "proteins"), fat=_number(nutriments, "fat"),
        carbs=_number(nutriments, "carbohydrates"), fiber=_number(nutriments, "fiber"),
        low_g=low_g if groups else None, high_g=high_g, groups=tuple(groups),
        allergens=tuple(sorted(allergens)), tags=tuple(sorted(tags)),
        portion=Portion(grams=_portion(product.get("serving_quantity")), label=_text(product.get("quantity"))),
        swaps=(), note=note, source="off", brand=brand, image=_safe_image(product.get("image_front_small_url")),
        ingredients=ingredients, estimated=bool(groups) and base is None, external_ref=f"off:{code}",
        unknown=unknown,
    )


def _safe_image(value) -> str:
    url = _text(value)
    return url if url.startswith("https://images.openfoodfacts.org/") else ""


class OpenFoodFacts:
    def __init__(self, cache: ExtrasRepo, user_agent: str, client: httpx.AsyncClient | None = None):
        self._cache = cache
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": user_agent})

    async def close(self) -> None:
        await self._client.aclose()

    async def is_cached(self, code: str) -> bool:
        return await self._cache.off_get(code) is not None

    async def product(self, code: str) -> dict | None:
        if not is_barcode(code):
            return None
        cached = await self._cache.off_get(code)
        if cached is not None:
            return None if cached.get("missing") else cached
        try:
            response = await self._client.get(PRODUCT_URL.format(code=code), params={"fields": FIELDS})
            # Неизвестный штрихкод OFF отдаёт как 404 — это «нет товара», а не сбой.
            if response.status_code != httpx.codes.NOT_FOUND:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("OFF product %s failed: %s", code, exc)
            raise OffUnavailable(str(exc)) from exc
        payload = {} if response.status_code == httpx.codes.NOT_FOUND else _json(response)
        product = payload.get("product") if payload.get("status") == 1 else None
        product = product if isinstance(product, dict) else None
        await self._cache.off_put(code, product or {"missing": True})
        return product

    async def search(self, query: str, limit: int = 12) -> list[dict]:
        """Поиск. Состав в выдаче не приходит, поэтому хиты не кешируем — карточка дозапросит товар."""
        params = {"q": query, "langs": "ru,en", "page_size": limit, "fields": FIELDS}
        try:
            response = await self._client.get(SEARCH_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("OFF search %r failed: %s", query, exc)
            raise OffUnavailable(str(exc)) from exc
        hits = _json(response).get("hits")
        return [hit for hit in hits if isinstance(hit, dict) and hit.get("code")] if isinstance(hits, list) else []
