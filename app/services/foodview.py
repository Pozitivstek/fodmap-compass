"""Поиск продукта по ссылке (cat:/off:/custom:) и сборка карточек для API."""

from __future__ import annotations

from dataclasses import asdict

from app.domain import ALLERGENS, CATEGORIES, FODMAP_GROUPS
from app.services import fodmap
from app.services.catalog import Catalog, Food, Portion
from app.services.nutrition import macros
from app.services.off import OpenFoodFacts, to_food
from app.storage.extras import ExtrasRepo
from app.storage.reactions import ToleranceRecord

SNAPSHOT_KEYS = ("category", "kcal", "protein", "fat", "carbs", "fiber", "low_g", "high_g", "groups",
                 "allergens", "tags", "estimated", "unknown")


def to_tolerance(record: ToleranceRecord | None) -> fodmap.Tolerance | None:
    if record is None:
        return None
    return fodmap.Tolerance(status=record.status, tested_g=record.tested_g, note=record.note,
                            ok_count=record.ok_count, bad_count=record.bad_count)


def snapshot(food: Food, loads: dict[str, float]) -> dict:
    data = asdict(food)
    result = {key: data[key] for key in SNAPSHOT_KEYS}
    result["portion"] = data["portion"]
    result["loads"] = {g: round(v, 3) for g, v in loads.items()}
    return result


def from_snapshot(ref: str, name: str, emoji: str, snap: dict) -> Food:
    portion = snap.get("portion") or {"grams": 100, "label": ""}
    return Food(
        id=ref.split(":", 1)[-1], name=name, aliases=(), en=(), category=snap.get("category", "custom"),
        emoji=emoji, kcal=snap.get("kcal", 0), protein=snap.get("protein", 0), fat=snap.get("fat", 0),
        carbs=snap.get("carbs", 0), fiber=snap.get("fiber", 0), low_g=snap.get("low_g"),
        high_g=snap.get("high_g"), groups=tuple(snap.get("groups", ())), allergens=tuple(snap.get("allergens", ())),
        tags=tuple(snap.get("tags", ())), portion=Portion(**portion), swaps=(), note="",
        estimated=bool(snap.get("estimated")), external_ref=ref, unknown=bool(snap.get("unknown")),
    )


def custom_to_food(data: dict) -> Food:
    return Food(
        id=f"custom_{data['id']}", name=data["name"], aliases=(), en=(), category="custom",
        emoji=data.get("emoji") or "⭐", kcal=data.get("kcal", 0), protein=data.get("protein", 0),
        fat=data.get("fat", 0), carbs=data.get("carbs", 0), fiber=data.get("fiber", 0),
        low_g=data.get("low_g"), high_g=None, groups=tuple(data.get("groups", ())),
        allergens=tuple(data.get("allergens", ())), tags=tuple(data.get("tags", ())),
        portion=Portion(grams=data.get("portion_g") or 100, label=""), swaps=(), note=data.get("note", ""),
        source="custom", external_ref=f"custom:{data['id']}",
    )


class FoodResolver:
    def __init__(self, catalog: Catalog, off: OpenFoodFacts, extras: ExtrasRepo):
        self._catalog, self._off, self._extras = catalog, off, extras

    async def resolve(self, ref: str, user_id: int) -> Food | None:
        kind, _, key = ref.partition(":")
        if kind == "cat":
            return self._catalog.food(key)
        if kind == "off":
            product = await self._off.product(key)
            return to_food(product, self._catalog) if product else None
        if kind == "custom" and key.isdigit():
            data = await self._extras.custom_food(user_id, int(key))
            return custom_to_food(data) if data else None
        return None


def brief(food: Food, verdict: fodmap.Verdict) -> dict:
    return {"ref": food.ref, "name": food.name, "emoji": food.emoji, "brand": food.brand,
            "category": food.category, "image": food.image, "source": food.source,
            "portion": {"grams": food.portion.grams, "label": food.portion.label},
            "kcal": food.kcal, "verdict": verdict.to_dict()}


def card(food: Food, verdict: fodmap.Verdict, record: ToleranceRecord | None, catalog: Catalog,
         profile: fodmap.Profile, tolerances: dict[str, ToleranceRecord]) -> dict:
    relevant = set(fodmap.relevant_groups(food, profile))
    swaps = []
    for swap_id in food.swaps:
        swap = catalog.food(swap_id)
        if swap:
            swap_verdict = fodmap.evaluate(swap, profile, tolerance=to_tolerance(tolerances.get(swap.ref)))
            swaps.append(brief(swap, swap_verdict))
    category = CATEGORIES.get(food.category, CATEGORIES["product"])
    return {
        **brief(food, verdict),
        "category_name": category["name"], "category_emoji": category["emoji"],
        "per100": {"kcal": food.kcal, "protein": food.protein, "fat": food.fat, "carbs": food.carbs,
                   "fiber": food.fiber},
        "per_portion": macros(food, food.portion.grams),
        "low_g": food.low_g, "high_g": food.high_g, "estimated": food.estimated, "unknown": food.unknown,
        "groups": [{"code": g, "name": FODMAP_GROUPS[g]["name"], "desc": FODMAP_GROUPS[g]["desc"],
                    "relevant": g in relevant} for g in food.groups],
        "allergens": [{"code": a, "name": ALLERGENS[a], "hit": a in profile.allergens} for a in food.allergens],
        "tags": list(food.tags), "note": food.note, "ingredients": food.ingredients,
        "tolerance": record.to_dict() if record else None,
        "swaps": swaps,
    }
