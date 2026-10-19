"""Схемы входящих запросов (валидация на границе API)."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.clock import is_valid_tz
from app.domain import ALLERGENS, CONDITIONS, FEELINGS, FODMAP_GROUPS, FOOD_TAGS, SYMPTOMS

MealCode = Literal["breakfast", "lunch", "dinner", "snack"]
THEMES = ("auto", "light", "dark", "mint", "sunset", "ocean", "lavender", "forest", "graphite")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
REF_RE = re.compile(r"^(cat:[a-z0-9_]{1,40}|off:\d{6,14}|custom:\d{1,10})$")


def _only(values: list[str], allowed, kind: str) -> list[str]:
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise ValueError(f"неизвестные {kind}: {', '.join(unknown)}")
    return list(dict.fromkeys(values))


def check_ref(value: str) -> str:
    if not REF_RE.match(value):
        raise ValueError("неверная ссылка на продукт")
    return value


class BodyIn(BaseModel):
    sex: Literal["male", "female"] | None = None
    birth_year: int | None = Field(default=None, ge=1920, le=2020)
    height: float | None = Field(default=None, ge=100, le=250)
    weight: float | None = Field(default=None, ge=25, le=350)
    activity: Literal["low", "light", "medium", "high"] | None = None
    goal: Literal["lose", "keep", "gain"] | None = None


class TargetsIn(BaseModel):
    kcal: float | None = Field(default=None, ge=800, le=6000)
    protein: float | None = Field(default=None, ge=10, le=400)
    fat: float | None = Field(default=None, ge=10, le=300)
    carbs: float | None = Field(default=None, ge=10, le=800)


class RemindersIn(BaseModel):
    enabled: bool | None = None
    meals: dict[MealCode, str] | None = None
    water: bool | None = None
    evening: bool | None = None
    after_meal_minutes: int | None = Field(default=None, ge=0, le=600)

    @field_validator("meals")
    @classmethod
    def _times(cls, value: dict | None) -> dict | None:
        for meal_time in (value or {}).values():
            if meal_time and not TIME_RE.match(meal_time):
                raise ValueError("время в формате ЧЧ:ММ")
        return value


class ProfileIn(BaseModel):
    conditions: list[str] | None = Field(default=None, max_length=len(CONDITIONS))
    diet_style: Literal["omnivore", "pescatarian", "vegetarian", "vegan"] | None = None
    dislikes: list[str] | None = Field(default=None, max_length=60)
    likes: list[str] | None = Field(default=None, max_length=60)
    tolerated_groups: list[str] | None = None
    body: BodyIn | None = None
    targets_override: TargetsIn | None = None
    water_goal_ml: int | None = Field(default=None, ge=500, le=6000)
    theme: Literal[THEMES] | None = None  # type: ignore[valid-type]
    tz: str | None = None
    reminders: RemindersIn | None = None
    onboarded: bool | None = None
    seen_achievements: list[str] | None = Field(default=None, max_length=50)

    @field_validator("conditions")
    @classmethod
    def _conditions(cls, value):
        return None if value is None else _only(value, CONDITIONS, "состояния")

    @field_validator("tolerated_groups")
    @classmethod
    def _groups(cls, value):
        return None if value is None else _only(value, FODMAP_GROUPS, "группы")

    @field_validator("dislikes", "likes")
    @classmethod
    def _words(cls, value):
        if value is None:
            return None
        words = [w.strip().lower()[:40] for w in value if w and w.strip()]
        return list(dict.fromkeys(words))

    @field_validator("tz")
    @classmethod
    def _tz(cls, value):
        if value is not None and not is_valid_tz(value):
            raise ValueError("неизвестный часовой пояс")
        return value


class EntryIn(BaseModel):
    ref: str
    day: date
    meal: MealCode
    grams: float = Field(gt=0, le=3000)

    @field_validator("ref")
    @classmethod
    def _ref(cls, value: str) -> str:
        return check_ref(value)


class EntryPatch(BaseModel):
    grams: float | None = Field(default=None, gt=0, le=3000)
    meal: MealCode | None = None


class ReactionIn(BaseModel):
    day: date
    meal: MealCode | None = None
    ref: str | None = None
    feeling: Literal[tuple(FEELINGS)]  # type: ignore[valid-type]
    symptoms: list[str] = Field(default_factory=list, max_length=len(SYMPTOMS))
    severity: int = Field(default=0, ge=0, le=5)
    note: str = Field(default="", max_length=500)
    grams: float | None = Field(default=None, gt=0, le=3000)

    @field_validator("symptoms")
    @classmethod
    def _symptoms(cls, value):
        return _only(value, SYMPTOMS, "симптомы")

    @field_validator("ref")
    @classmethod
    def _ref(cls, value):
        return None if value is None else check_ref(value)


class ToleranceIn(BaseModel):
    status: Literal["ok", "caution", "avoid"]
    tested_g: float | None = Field(default=None, gt=0, le=3000)
    note: str = Field(default="", max_length=300)
    name: str = Field(default="", max_length=120)


class CustomFoodIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    emoji: str = Field(default="⭐", max_length=8)
    kcal: float = Field(default=0, ge=0, le=900)
    protein: float = Field(default=0, ge=0, le=100)
    fat: float = Field(default=0, ge=0, le=100)
    carbs: float = Field(default=0, ge=0, le=100)
    fiber: float = Field(default=0, ge=0, le=100)
    groups: list[str] = Field(default_factory=list)
    allergens: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    low_g: float | None = Field(default=None, gt=0, le=3000)
    portion_g: float = Field(default=100, gt=0, le=3000)
    note: str = Field(default="", max_length=300)

    @field_validator("groups")
    @classmethod
    def _g(cls, v):
        return _only(v, FODMAP_GROUPS, "группы")

    @field_validator("allergens")
    @classmethod
    def _a(cls, v):
        return _only(v, ALLERGENS, "аллергены")

    @field_validator("tags")
    @classmethod
    def _t(cls, v):
        return _only(v, FOOD_TAGS, "метки")


class WaterIn(BaseModel):
    delta_ml: int = Field(ge=-5000, le=5000)
    day: date | None = None


class RecipeLogIn(BaseModel):
    day: date
    meal: MealCode
    servings: float = Field(default=1, gt=0, le=10)


class ShoppingIn(BaseModel):
    names: list[str] = Field(min_length=1, max_length=50)

    @field_validator("names")
    @classmethod
    def _names(cls, value):
        return [n.strip()[:80] for n in value if n.strip()]


class ShoppingPatch(BaseModel):
    done: bool


class ReportIn(BaseModel):
    days: int = Field(default=30, ge=7, le=90)

