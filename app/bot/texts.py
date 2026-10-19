"""Тексты и клавиатуры бота."""

from __future__ import annotations

from html import escape
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.domain import FEELINGS, MEALS
from app.services import fodmap
from app.services.catalog import Food
from app.services.nutrition import macros

LEVEL_EMOJI = {fodmap.GREEN: "🟢", fodmap.YELLOW: "🟡", fodmap.RED: "🔴", fodmap.GREY: "⚪"}

WELCOME = (
    "Привет, {name}! Я <b>ФудКомпас</b> 🧭 — помощник для тех, кто на <b>low-FODMAP</b>, "
    "с непереносимостью лактозы, глютена или пищевой аллергией.\n\n"
    "• Подскажу, можно ли продукт и в какой порции\n"
    "• Сканирую штрихкоды и разбираю состав\n"
    "• Веду дневник еды и самочувствия, считаю КБЖУ\n"
    "• Запоминаю, что подходит именно вам\n"
    "• Предлагаю рецепты под ваши ограничения\n\n"
    "Откройте приложение кнопкой ниже. А ещё можно просто написать мне название продукта "
    "или прислать фото штрихкода."
)

HELP = (
    "<b>Что я умею</b>\n"
    "✍️ Напишите продукт — «можно ли авокадо?»\n"
    "📷 Пришлите фото штрихкода — разберу состав\n"
    "/today — сводка за сегодня\n"
    "/report — PDF-отчёт за 30 дней для врача\n"
    "/app — открыть приложение\n\n"
    "Справочник основан на открытых данных Monash University. Это не замена консультации гастроэнтеролога."
)


def route_url(url: str, route: str = "") -> str:
    """Маршрут передаём в query: в #hash Telegram дописывает свои параметры запуска."""
    return url + (f"?route={quote(route, safe='')}" if route else "")


def app_button(url: str, text: str = "🧭 Открыть ФудКомпас", route: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text, web_app=WebAppInfo(url=route_url(url, route)))]])


def food_text(food: Food, verdict: fodmap.Verdict) -> str:
    title = escape(food.name) + (f" · {escape(food.brand)}" if food.brand else "")
    lines = [f"{food.emoji} <b>{title}</b>", f"{LEVEL_EMOJI[verdict.level]} <b>{verdict.title}</b>"]
    lines += [f"— {escape(reason)}" for reason in verdict.reasons]
    if verdict.safe_g:
        lines.append(f"Безопасная порция: до <b>{verdict.safe_g:g} г</b>")
    per100 = macros(food, 100)
    lines.append(f"На 100 г: {per100['kcal']:g} ккал · Б {per100['protein']:g} · Ж {per100['fat']:g} · "
                 f"У {per100['carbs']:g}")
    if food.note:
        lines.append(f"<i>{escape(food.note)}</i>")
    return "\n".join(lines)


def reaction_keyboard(prompt_id: int, url: str, day: str, meal: str) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=f"{spec['emoji']} {spec['name']}", callback_data=f"rx:{prompt_id}:{code}")
               for code, spec in FEELINGS.items()]
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons[:2], buttons[2:],
        [InlineKeyboardButton(text="✍️ Подробнее: симптомы и заметка",
                              web_app=WebAppInfo(url=route_url(url, f"/react?day={day}&meal={meal}")))],
    ])


def prompt_text(meal: str, names: list[str]) -> str:
    spec = MEALS.get(meal, MEALS["snack"])
    eaten = ", ".join(escape(n) for n in names[:6]) or "—"
    return (f"{spec['emoji']} Как самочувствие после приёма «{spec['name'].lower()}»?\n"
            f"<i>Вы ели: {eaten}</i>\n\nОтвет обновит личные отметки этих продуктов.")
