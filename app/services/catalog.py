"""Каталог продуктов и рецептов: загрузка из data/, проверка и поиск."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from app.domain import ALLERGENS, CATEGORIES, FODMAP_GROUPS, FOOD_TAGS

FOOD_FIELDS = 19
MIN_FUZZY_SCORE = 0.72
MIN_TYPO_RATIO = 0.82


@dataclass(frozen=True)
class Portion:
    grams: float
    label: str


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    aliases: tuple[str, ...]
    en: tuple[str, ...]
    category: str
    emoji: str
    kcal: float
    protein: float
    fat: float
    carbs: float
    fiber: float
    low_g: float | None
    high_g: float | None
    groups: tuple[str, ...]
    allergens: tuple[str, ...]
    tags: tuple[str, ...]
    portion: Portion
    swaps: tuple[str, ...]
    note: str
    source: str = "catalog"
    brand: str = ""
    image: str = ""
    ingredients: str = ""
    estimated: bool = False
    external_ref: str = ""
    unknown: bool = False  # товар без состава и без похожего продукта — оценить нельзя

    @property
    def ref(self) -> str:
        return self.external_ref or f"cat:{self.id}"

    @property
    def fodmap_free(self) -> bool:
        return not self.groups


@dataclass(frozen=True)
class RecipeIngredient:
    food_id: str
    grams: float
    note: str = ""


@dataclass(frozen=True)
class Recipe:
    id: str
    title: str
    emoji: str
    meals: tuple[str, ...]
    minutes: int
    servings: int
    description: str
    ingredients: tuple[RecipeIngredient, ...]
    steps: tuple[str, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)


class CatalogError(ValueError):
    """Ошибка в файлах данных каталога."""


def normalize(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def _split(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _number(value: str, line_no: int) -> float | None:
    if not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise CatalogError(f"строка {line_no}: «{value}» не число") from exc


def _check_codes(codes: tuple[str, ...], allowed: dict | set, kind: str, line_no: int) -> None:
    unknown = [code for code in codes if code not in allowed]
    if unknown:
        raise CatalogError(f"строка {line_no}: неизвестные {kind}: {', '.join(unknown)}")


def _parse_portion(value: str, line_no: int) -> Portion:
    grams, _, label = value.partition(":")
    amount = _number(grams, line_no)
    if amount is None or amount <= 0:
        raise CatalogError(f"строка {line_no}: порция должна быть «граммы:описание»")
    return Portion(grams=amount, label=label.strip())


def parse_food_line(line: str, line_no: int) -> Food:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) != FOOD_FIELDS:
        raise CatalogError(f"строка {line_no}: ожидалось {FOOD_FIELDS} полей, получено {len(parts)}")
    (food_id, name, aliases, en, category, emoji, kcal, protein, fat, carbs, fiber,
     low_g, high_g, groups, allergens, tags, portion, swaps, note) = parts
    groups_t, allergens_t, tags_t = _split(groups), _split(allergens), _split(tags)
    _check_codes(groups_t, FODMAP_GROUPS, "группы FODMAP", line_no)
    _check_codes(allergens_t, ALLERGENS, "аллергены", line_no)
    _check_codes(tags_t, FOOD_TAGS, "метки", line_no)
    if category not in CATEGORIES:
        raise CatalogError(f"строка {line_no}: неизвестная категория {category}")
    low, high = _number(low_g, line_no), _number(high_g, line_no)
    if (low is not None or high is not None) and not groups_t:
        raise CatalogError(f"строка {line_no}: порции заданы, а группы FODMAP пустые")
    if low is not None and high is not None and high < low:
        raise CatalogError(f"строка {line_no}: high_g меньше low_g")
    nutrients = [_number(value, line_no) for value in (kcal, protein, fat, carbs, fiber)]
    if any(value is None for value in nutrients):
        raise CatalogError(f"строка {line_no}: не заполнено КБЖУ")
    return Food(
        id=food_id, name=name, aliases=_split(aliases), en=_split(en), category=category,
        emoji=emoji, kcal=nutrients[0], protein=nutrients[1], fat=nutrients[2], carbs=nutrients[3],
        fiber=nutrients[4], low_g=low, high_g=high, groups=groups_t, allergens=allergens_t,
        tags=tags_t, portion=_parse_portion(portion, line_no), swaps=_split(swaps), note=note,
    )


def load_foods(path: Path) -> dict[str, Food]:
    foods: dict[str, Food] = {}
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        food = parse_food_line(line, line_no)
        if food.id in foods:
            raise CatalogError(f"строка {line_no}: повтор id {food.id}")
        foods[food.id] = food
    missing = sorted({swap for food in foods.values() for swap in food.swaps} - foods.keys())
    if missing:
        raise CatalogError(f"замены ссылаются на несуществующие продукты: {', '.join(missing)}")
    return foods


def load_recipes(path: Path, foods: dict[str, Food]) -> dict[str, Recipe]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    recipes: dict[str, Recipe] = {}
    for item in raw:
        ingredients = tuple(
            RecipeIngredient(food_id=ing["food"], grams=float(ing["g"]), note=ing.get("note", ""))
            for ing in item["ingredients"]
        )
        unknown = [ing.food_id for ing in ingredients if ing.food_id not in foods]
        if unknown:
            raise CatalogError(f"рецепт {item['id']}: нет продуктов {', '.join(unknown)}")
        recipes[item["id"]] = Recipe(
            id=item["id"], title=item["title"], emoji=item.get("emoji", "🍽️"),
            meals=tuple(item["meals"]), minutes=int(item["minutes"]), servings=int(item["servings"]),
            description=item.get("description", ""), ingredients=ingredients,
            steps=tuple(item["steps"]), tags=tuple(item.get("tags", [])),
        )
    return recipes


def _match_score(query: str, food: Food) -> float:
    names = [normalize(food.name), *map(normalize, food.aliases), *map(normalize, food.en)]
    best = 0.0
    for name in names:
        if name == query:
            return 1.0
        if name.startswith(query):
            best = max(best, 0.95)
        elif any(word.startswith(query) for word in name.split()):
            best = max(best, 0.9)
        elif query in name:
            best = max(best, 0.8)
        elif len(query) >= 4:
            ratio = SequenceMatcher(None, query, name).ratio()
            best = max(best, ratio if ratio >= MIN_TYPO_RATIO else 0.0)
    return best


class Catalog:
    """Справочник в памяти: только чтение после загрузки."""

    def __init__(self, foods: dict[str, Food], recipes: dict[str, Recipe]):
        self._foods = foods
        self._recipes = recipes

    @classmethod
    def from_dir(cls, data_dir: Path) -> "Catalog":
        foods = load_foods(data_dir / "foods.psv")
        recipes = load_recipes(data_dir / "recipes.json", foods)
        return cls(foods, recipes)

    @property
    def foods(self) -> dict[str, Food]:
        return dict(self._foods)

    @property
    def recipes(self) -> dict[str, Recipe]:
        return dict(self._recipes)

    def food(self, food_id: str) -> Food | None:
        return self._foods.get(food_id)

    def recipe(self, recipe_id: str) -> Recipe | None:
        return self._recipes.get(recipe_id)

    def by_category(self, category: str) -> list[Food]:
        return sorted((f for f in self._foods.values() if f.category == category), key=lambda f: f.name)

    def search(self, query: str, limit: int = 30) -> list[Food]:
        needle = normalize(query)
        if not needle:
            return []
        scored = [(score, food) for food in self._foods.values()
                  if (score := _match_score(needle, food)) >= MIN_FUZZY_SCORE]
        scored.sort(key=lambda pair: (-pair[0], len(pair[1].name)))
        return [food for _, food in scored[:limit]]

    def best_name_match(self, text: str) -> Food | None:
        """Продукт, чьё название раньше всех встречается в тексте («Йогурт Персик» → йогурт)."""
        haystack = normalize(text)
        best: tuple[int, int, Food] | None = None
        for food in self._foods.values():
            for name in (food.name, *food.aliases):
                needle = normalize(name)
                found = re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) if len(needle) >= 4 else None
                if not found:
                    continue
                pos = found.start()
                candidate = (pos, -len(needle), food)
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
        return best[2] if best else None

    def find_in_text(self, text: str) -> list[Food]:
        """Продукты каталога, чьё название встречается в тексте (для разбора англ. ингредиентов)."""
        haystack = normalize(text)
        found = []
        for food in self._foods.values():
            names = [normalize(n) for n in (food.name, *food.aliases, *food.en)]
            if any(len(n) > 2 and n in haystack for n in names):
                found.append(food)
        return found
