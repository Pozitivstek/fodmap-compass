"""Оценка порций, аллергенов, личного опыта и накопления FODMAP."""

from app.services import fodmap
from app.services.fodmap import GREEN, GREY, RED, YELLOW, Profile, Tolerance, evaluate, stack

FODMAP = Profile(conditions=("fodmap",))


def test_profile_from_settings_collects_groups_and_allergens():
    profile = Profile.from_settings({"conditions": ["lactose", "celiac", "fructose"], "dislikes": ["Грибы"],
                                     "tolerated_groups": ["sor"]})
    assert profile.fodmap_groups == {"lac", "fru"}
    assert profile.allergens == {"gluten"}
    assert profile.dislikes == ("грибы",)


def test_portion_traffic_light(catalog):
    avocado = catalog.food("avocado")
    assert evaluate(avocado, FODMAP, 30).level == GREEN
    assert evaluate(avocado, FODMAP, 50).level == YELLOW
    assert evaluate(avocado, FODMAP, 100).level == RED
    assert evaluate(avocado, FODMAP, 30).safe_g == 30


def test_no_safe_portion_and_free_food(catalog):
    garlic = evaluate(catalog.food("garlic"), FODMAP)
    assert garlic.level == RED and garlic.safe_g == 0
    chicken = evaluate(catalog.food("chicken_breast"), FODMAP, 300)
    assert chicken.level == GREEN and chicken.loads == {}


def test_unrelated_conditions_do_not_restrict(catalog):
    lactose_only = Profile(conditions=("lactose",))
    assert evaluate(catalog.food("garlic"), lactose_only).level == GREEN
    assert evaluate(catalog.food("milk"), lactose_only, 200).level == RED
    assert evaluate(catalog.food("milk_lf"), lactose_only, 200).reasons == ("Без лактозы — подходит",)


def test_allergy_beats_personal_experience(catalog):
    celiac = Profile(conditions=("celiac",))
    verdict = evaluate(catalog.food("bread_wheat"), celiac, tolerance=Tolerance(status="ok"))
    assert verdict.level == RED and verdict.allergy
    assert verdict.personal is None


def test_diet_style_and_dislikes(catalog):
    vegan = Profile(diet_style="vegan", dislikes=("кинза",))
    assert evaluate(catalog.food("beef"), vegan).level == GREY
    assert evaluate(catalog.food("cilantro"), vegan).disliked


def test_personal_tolerance_overrides_portion(catalog):
    avocado = catalog.food("avocado")
    ok = Tolerance(status="ok", tested_g=100)
    assert evaluate(avocado, FODMAP, 100, ok).level == GREEN
    assert evaluate(avocado, FODMAP, 100, ok).loads == {}
    assert evaluate(avocado, FODMAP, 150, ok).level == YELLOW
    assert evaluate(avocado, FODMAP, 10, Tolerance(status="avoid")).level == RED
    assert evaluate(avocado, FODMAP, 10, Tolerance(status="caution")).level == YELLOW


def test_estimated_products(catalog):
    from dataclasses import replace
    product = replace(catalog.food("yogurt"), estimated=True, low_g=None)
    assert evaluate(product, FODMAP).level == RED
    assert evaluate(replace(product, low_g=100), FODMAP).level == YELLOW


def test_stack_sums_loads_across_foods():
    assert stack([]) == {"level": GREEN, "groups": {}, "short": "Нагрузка в норме", "message": "Нагрузка в норме"}
    caution = stack([{"fruc": 0.8}, {"fruc": 0.6}])
    assert caution["level"] == YELLOW and "фруктаны" in caution["short"]
    assert stack([{"fruc": 1.5}, {"fruc": 1.0}])["level"] == RED


def test_worst_level_order():
    assert fodmap.worst([GREEN, GREY, YELLOW]) == YELLOW
    assert fodmap.worst([]) == GREEN
    assert evaluate.__name__ == "evaluate"
