"""Каталог: целостность данных, разбор строк, поиск."""

import pytest

from app.domain import FODMAP_GROUPS
from app.services.catalog import CatalogError, load_foods, parse_food_line

GOOD = "apple|Яблоко|яблоки|apple|fruit|🍎|52|0.3|0.2|14|2.4|20|40|fru,sor|||150:1 среднее||"


def test_catalog_has_hundreds_of_foods_and_recipes(catalog):
    assert len(catalog.foods) >= 300
    assert len(catalog.recipes) >= 25


def test_every_food_with_portions_has_groups(catalog):
    for food in catalog.foods.values():
        if food.low_g is not None:
            assert food.groups, food.id
        assert set(food.groups) <= set(FODMAP_GROUPS)


def test_recipes_reference_existing_foods(catalog):
    for recipe in catalog.recipes.values():
        assert all(catalog.food(i.food_id) for i in recipe.ingredients)
        assert recipe.steps


def test_parse_good_line():
    food = parse_food_line(GOOD, 1)
    assert food.ref == "cat:apple"
    assert food.groups == ("fru", "sor")
    assert food.portion.grams == 150
    assert not food.fodmap_free


@pytest.mark.parametrize("line, message", [
    ("a|b|c", "ожидалось"),
    (GOOD.replace("fru,sor", "xxx"), "группы"),
    (GOOD.replace("|20|40|", "|40|20|"), "high_g"),
    (GOOD.replace("|20|40|fru,sor|", "|20|40||"), "группы FODMAP пустые"),
    (GOOD.replace("|fruit|", "|space|"), "категория"),
    (GOOD.replace("|52|", "|много|"), "не число"),
    (GOOD.replace("150:1 среднее", "абв"), "не число"),
])
def test_parse_rejects_bad_lines(line, message):
    with pytest.raises(CatalogError, match=message):
        parse_food_line(line, 7)


def test_load_rejects_duplicates_and_bad_swaps(tmp_path):
    path = tmp_path / "foods.psv"
    path.write_text(f"{GOOD}\n{GOOD}\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="повтор"):
        load_foods(path)
    path.write_text(GOOD[:-2] + "|ghost|\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="ghost"):
        load_foods(path)


def test_search_exact_prefix_and_typo(catalog):
    assert catalog.search("Авокадо")[0].id == "avocado"
    assert catalog.search("банан")[0].id.startswith("banana")
    assert catalog.search("avocado")[0].id == "avocado"
    assert catalog.search("клубнка")[0].id == "strawberry"
    assert catalog.search("") == []
    assert "turnip" not in [f.id for f in catalog.search("гречка")]


def test_name_matching_helpers(catalog):
    assert catalog.best_name_match("Био Йогурт Персик").id == "yogurt"
    assert catalog.best_name_match("Непонятный товар") is None
    found = {f.id for f in catalog.find_in_text("2 cloves garlic, 1 onion, rice")}
    assert {"garlic", "onion", "rice_white"} <= found
    assert catalog.by_category("spice")
