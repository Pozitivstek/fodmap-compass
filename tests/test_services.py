"""Разбор состава, КБЖУ, серия дней, переносимость, аналитика, подпись Telegram."""

import json
import time
from datetime import date
from urllib.parse import urlencode

import pytest

from app.api.auth import InitDataError, sign, validate
from app.services import insights, nutrition, streak
from app.services.ingredients import analyze
from app.services.tolerance import apply_reaction, derive_status, pick_suspects, set_manual
from app.storage.diary import DiaryEntry
from app.storage.reactions import Reaction
from tests.conftest import BOT_TOKEN

# ---------- состав ----------


def test_onion_and_garlic_are_strong_triggers():
    result = analyze("картофель, масло, соль, чеснок сушёный, лук")
    assert result.groups["fruc"] == "high"
    assert result.strong


def test_negations_and_infused_oil():
    result = analyze("молоко безлактозное, масло настоянное на чесноке, зелёный лук")
    assert "lac" not in result.groups
    assert result.lactose_free
    assert "fruc" not in result.groups


def test_minor_wheat_is_only_possible_and_allergens_found():
    result = analyze("рис, кукуруза, сахар, соль, пшеничная мука", ["en:soybeans"])
    assert result.groups["fruc"] == "possible"
    assert {"gluten", "soy"} <= set(result.allergens)


def test_polyols_and_tags():
    result = analyze("подсластитель сорбит (E420), шоколад, яичный порошок, мёд")
    assert result.groups["sor"] == "high"
    assert result.groups["fru"] == "high"
    assert {"egg", "honey"} <= set(result.tags)


def test_empty_text():
    assert analyze("").groups == {}

# ---------- КБЖУ ----------


def test_macros_and_totals(catalog):
    values = nutrition.macros(catalog.food("rice_white"), 50)
    assert values["kcal"] == pytest.approx(172, abs=1)
    assert nutrition.total([values, values])["kcal"] == pytest.approx(344, abs=1)


def test_targets_default_mifflin_and_override():
    assert nutrition.targets({}) == nutrition.DEFAULT_TARGETS
    body = {"sex": "female", "birth_year": 1995, "height": 168, "weight": 62, "activity": "light", "goal": "keep"}
    result = nutrition.targets(body, today=date(2026, 1, 1))
    assert 1800 < result["kcal"] < 2100
    assert nutrition.targets(body, {"kcal": 1500}, today=date(2026, 1, 1))["kcal"] == 1500
    assert nutrition.water_goal(body, 2000) == 1860
    assert nutrition.water_goal({}, 2000) == 2000

# ---------- серия ----------


def test_streak_alive_at_risk_and_best():
    today = date(2026, 10, 20)
    days = {"2026-10-19", "2026-10-18", "2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13"}
    run = streak.compute(days, today)
    assert (run.current, run.best, run.at_risk, run.today_logged) == (2, 4, True, False)
    assert streak.compute(days | {"2026-10-20"}, today).current == 3
    assert streak.compute(set(), today).current == 0


def test_achievements_progress():
    items = {a["code"]: a for a in streak.achievements({"best_streak": 7, "entries": 1})}
    assert items["streak_7"]["earned"] and not items["streak_14"]["earned"]
    assert items["first_entry"]["earned"]
    assert items["streak_30"]["progress"] == 7

# ---------- переносимость ----------


def test_derive_status():
    assert derive_status(0, 0, 1) == "avoid"
    assert derive_status(3, 0, 2) == "avoid"
    assert derive_status(1, 2, 0) == "caution"
    assert derive_status(2, 1, 0) == "ok"


def test_apply_reaction_tracks_tested_grams_and_respects_manual():
    record = apply_reaction(None, "cat:apple", "Яблоко", "great", 50)
    record = apply_reaction(record, "cat:apple", "Яблоко", "ok", 80)
    assert (record.status, record.tested_g, record.ok_count) == ("ok", 80, 2)
    record = apply_reaction(record, "cat:apple", "", "bad", 100)
    assert record.bad_count == 1 and record.name == "Яблоко"
    manual = set_manual(record, "cat:apple", "", "avoid", None, "точно нет")
    assert apply_reaction(manual, "cat:apple", "", "great", 10).status == "avoid"
    with pytest.raises(ValueError):
        set_manual(None, "cat:apple", "x", "maybe", None, "")


def test_pick_suspects():
    foods = [("cat:rice", "Рис", 100, False), ("cat:apple", "Яблоко", 150, True)]
    assert [s[0] for s in pick_suspects(foods, "bad")] == ["cat:apple"]
    assert len(pick_suspects(foods, "great")) == 2
    assert len(pick_suspects([("cat:rice", "Рис", 100, False)], "bad")) == 1

# ---------- аналитика ----------


def _entry(i, day, meal, ref, name, created, loads=None):
    return DiaryEntry(id=i, day=day, meal=meal, ref=ref, name=name, emoji="🍽", grams=100,
                      macros={"kcal": 100, "protein": 1, "fat": 1, "carbs": 1, "fiber": 1},
                      food={"loads": loads or {}}, created_at=created)


def _reaction(i, day, feeling, meal=None, refs=(), created="2026-10-01T12:00:00+00:00", symptoms=()):
    return Reaction(id=i, day=day, meal=meal, ref=None, feeling=feeling, symptoms=tuple(symptoms), severity=0,
                    note="", refs=tuple(refs), created_at=created)


def test_insights_find_suspects_and_safe_foods():
    entries = [
        _entry(1, "2026-10-01", "lunch", "cat:apple", "Яблоко", "2026-10-01T10:00:00+00:00", {"fru": 3}),
        _entry(2, "2026-10-02", "lunch", "cat:apple", "Яблоко", "2026-10-02T10:00:00+00:00", {"fru": 3}),
        _entry(3, "2026-10-01", "dinner", "cat:rice", "Рис", "2026-10-01T15:00:00+00:00"),
        _entry(4, "2026-10-02", "dinner", "cat:rice", "Рис", "2026-10-02T15:00:00+00:00"),
    ]
    reactions = [
        _reaction(1, "2026-10-01", "bad", meal="lunch", symptoms=["bloating"]),
        _reaction(2, "2026-10-02", "bad", refs=["cat:apple"]),
        _reaction(3, "2026-10-02", "great", meal="dinner"),
        _reaction(4, "2026-10-01", "mild", created="2026-10-01T09:00:00+00:00"),
    ]
    data = insights.build(["2026-10-01", "2026-10-02"], entries, reactions, {"2026-10-01": 500})
    assert data["suspects"][0]["ref"] == "cat:apple"
    assert data["safe"][0]["ref"] == "cat:rice"
    assert data["groups"][0]["group"] == "fru"
    assert data["symptoms"][0]["code"] == "bloating"
    assert data["days"][0]["water"] == 500 and data["days"][0]["score"] == 4
    assert data["logged_days"] == 2

# ---------- подпись Telegram ----------


def _init_data(user=None, auth_date=None, token=BOT_TOKEN):
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAA",
              "user": json.dumps(user or {"id": 7, "first_name": "Аня"}, ensure_ascii=False)}
    return urlencode({**fields, "hash": sign(fields, token)})


def test_validate_init_data():
    assert validate(_init_data(), BOT_TOKEN, 3600)["id"] == 7


@pytest.mark.parametrize("data, message", [
    ("", "нет данных"),
    (_init_data(token="999:OTHER"), "подпись"),
    (_init_data(auth_date=1), "устарела"),
    (_init_data(user={"name": "без id"}), "нет пользователя"),
])
def test_validate_rejects(data, message):
    with pytest.raises(InitDataError, match=message):
        validate(data, BOT_TOKEN, 3600)
