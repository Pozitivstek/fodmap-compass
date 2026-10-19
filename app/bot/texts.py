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

# Ответ на /start: все функции бота простыми словами. Должен влезать в одно сообщение Telegram (4096 символов).
TELEGRAM_TEXT_LIMIT = 4096

WELCOME = (
    "Привет, {name}! 👋 Я <b>ФудКомпас</b> 🧭\n"
    "Помогаю тем, кому нельзя есть всё подряд: чувствительный живот (диета low-FODMAP), "
    "непереносимость молока или глютена, аллергия. FODMAP — вещества в еде, от которых у таких людей "
    "пучит живот.\n\n"
    "👋 <b>Знакомство.</b> Сначала спрошу, что тебе нельзя, как ты питаешься, что не любишь, "
    "рост и вес (для нормы калорий) и какую тему оформления выбрать.\n\n"
    "🔍 <b>Можно ли съесть?</b> 320 продуктов: 🟢 можно, 🟡 осторожно, 🔴 нельзя. "
    "Двигаешь граммы — видно, <b>сколько можно без вреда</b>. Есть калории, белки, жиры, углеводы, "
    "аллергены и <b>чем заменить</b>.\n\n"
    "🛒 <b>Товары из магазина.</b> Найди по названию или <b>отсканируй штрихкод</b> — "
    "прочитаю состав и скажу, есть ли там лук, чеснок, мёд, молоко и т. д.\n\n"
    "💬 <b>Прямо в чате.</b> Напиши «можно ли авокадо?» или пришли фото штрихкода.\n\n"
    "📒 <b>Дневник.</b> Записывай завтрак, обед, ужин и перекусы. Посчитаю калории, "
    "предупрежу, если безопасные продукты <b>вместе дали слишком много</b>. Есть учёт воды 💧\n\n"
    "🩺 <b>Самочувствие.</b> После еды отметь: 😊 отлично, 🙂 нормально, 😕 дискомфорт, 😣 плохо. "
    "Можно выбрать симптомы, силу и <b>написать своими словами</b>.\n\n"
    "💚 <b>Личные пометки.</b> По твоим отметкам продукт станет «подходит мне», «осторожно» "
    "или «не подходит» — <b>только у тебя</b>.\n\n"
    "🔥 <b>Огонёк</b> — сколько дней подряд ведёшь дневник, плюс 12 наград.\n\n"
    "🏠 <b>Главная.</b> Огонёк, калории, вода, <b>«что съесть сейчас»</b> и совет дня.\n\n"
    "🍳 <b>Рецепты.</b> 30 безопасных рецептов на русском. «Я приготовил» — запишу в дневник, "
    "«В покупки» — добавлю в список покупок 🛒\n\n"
    "📊 <b>Анализ.</b> График самочувствия, какие продукты вызывают проблемы, "
    "и <b>PDF-отчёт для врача</b> прямо в чат.\n\n"
    "🔔 <b>Напоминания.</b> Про еду, воду, пустой день, а после еды спрошу «как самочувствие?» — "
    "ответ одной кнопкой.\n\n"
    "🎨 9 тем оформления. ⚙️ Всё можно поменять в настройках или удалить свои данные.\n\n"
    "⌨️ /app — приложение · /today — сегодня · /report — отчёт врачу · /help — подсказка\n\n"
    "⚠️ Я подсказчик, а не врач. При сильных симптомах иди к гастроэнтерологу.\n\n"
    "👇 Открывай <b>ФудКомпас</b> кнопкой ниже."
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
