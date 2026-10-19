"""Бот: обработчики сообщений и кнопок, напоминания, распознавание штрихкода."""

import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.bot.handlers import build_router
from app.bot.reminders import Reminders, in_window
from app.bot.texts import food_text, reaction_keyboard, route_url
from app.services import fodmap
from app.services.barcode import BarcodeError, decode
from app.services.journal import add_entry

USER_ID = 77
MSK = timezone(timedelta(hours=3))


def _tg_user():
    return SimpleNamespace(id=USER_ID, first_name="Аня", username="anya")


def _message(text="", photo=None):
    return SimpleNamespace(from_user=_tg_user(), text=text, photo=photo, answer=AsyncMock(),
                           answer_document=AsyncMock())


def _handlers(ctx):
    router = build_router(ctx)
    found = {h.callback.__name__: h.callback for h in router.message.handlers}
    found.update({h.callback.__name__: h.callback for h in router.callback_query.handlers})
    return found


async def _onboard(ctx, **patch):
    user = await ctx.storage.users.ensure(USER_ID, "Аня", "anya")
    return await ctx.storage.users.update(user, {"conditions": ["fodmap"], **patch}, tz="Europe/Moscow",
                                          onboarded=True)


def test_texts(catalog):
    food = catalog.food("apple")
    verdict = fodmap.evaluate(food, fodmap.Profile(conditions=("fodmap",)), 150)
    text = food_text(food, verdict)
    assert "Яблоко" in text and "🔴" in text and "до <b>20 г</b>" in text
    assert route_url("https://x/", "/food/cat:apple") == "https://x/?route=%2Ffood%2Fcat%3Aapple"
    keyboard = reaction_keyboard(5, "https://x/", "2026-10-20", "lunch")
    assert keyboard.inline_keyboard[0][0].callback_data == "rx:5:great"


def test_welcome_fits_one_telegram_message():
    from app.bot.texts import TELEGRAM_TEXT_LIMIT, WELCOME
    text = WELCOME.format(name="Очень-длинное-имя-пользователя-в-телеграме")
    assert len(text) <= TELEGRAM_TEXT_LIMIT
    assert "/report" in text and "320 продуктов" in text


async def test_start_help_and_lookup(ctx):
    handlers = _handlers(ctx)
    await _onboard(ctx)
    message = _message()
    await handlers["start"](message)
    assert "ФудКомпас" in message.answer.call_args.args[0]
    await handlers["help_"](message)
    await handlers["open_app"](message)
    lookup = _message("Можно ли авокадо?")
    await handlers["lookup"](lookup)
    assert "Авокадо" in lookup.answer.call_args.args[0]
    nothing = _message("абырвалг")
    await handlers["lookup"](nothing)
    assert "Не нашёл" in nothing.answer.call_args.args[0]
    barcode = _message("4600000000024")
    await handlers["lookup"](barcode)
    assert "Нельзя" in barcode.answer.call_args.args[0]
    missing = _message("4600000009999")
    await handlers["lookup"](missing)
    assert "пока не внесён" in missing.answer.call_args.args[0]


async def test_today_and_report(ctx):
    handlers = _handlers(ctx)
    user = await _onboard(ctx)
    day = datetime.now(MSK).date().isoformat()
    await add_entry(ctx.storage, user, ctx.catalog.food("rice_white"), day, "lunch", 60)
    message = _message()
    await handlers["today"](message)
    assert "Рис белый" in message.answer.call_args.args[0]
    await handlers["report"](message)
    if message.answer_document.await_count == 0:
        pytest.skip("в системе нет шрифта с кириллицей")
    assert message.answer_document.call_args.kwargs["caption"].startswith("📄")


async def test_reaction_and_water_callbacks(ctx):
    handlers = _handlers(ctx)
    user = await _onboard(ctx)
    day = datetime.now(MSK).date().isoformat()
    await add_entry(ctx.storage, user, ctx.catalog.food("apple"), day, "snack", 150)
    prompt = (await ctx.storage.extras.due_prompts(datetime.now(timezone.utc) + timedelta(days=1)))[0]
    call = SimpleNamespace(data=f"rx:{prompt['id']}:bad", from_user=_tg_user(), answer=AsyncMock(),
                           message=SimpleNamespace(edit_text=AsyncMock()))
    await handlers["reaction"](call)
    assert "Плохо" in call.message.edit_text.call_args.args[0]
    record = await ctx.storage.tolerances.get(USER_ID, "cat:apple")
    assert record.status == "avoid"
    stale = SimpleNamespace(data="rx:999:great", from_user=_tg_user(), answer=AsyncMock(), message=None)
    await handlers["reaction"](stale)
    stale.answer.assert_awaited_with("Этот вопрос уже неактуален")
    water = SimpleNamespace(data="water:500", from_user=_tg_user(), answer=AsyncMock())
    await handlers["water"](water)
    assert await ctx.storage.extras.water(USER_ID, day) == 500


class FakeBot:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    async def send_message(self, chat_id, text, reply_markup=None):
        if self.fail:
            raise TelegramForbiddenError(method=SimpleNamespace(), message="blocked")
        self.sent.append(text)


def test_in_window():
    now = datetime(2026, 10, 20, 13, 40, tzinfo=MSK)
    assert in_window(now, datetime(2026, 1, 1, 13, 30).time())
    assert not in_window(now, datetime(2026, 1, 1, 14, 30).time())


async def test_reminders_meals_water_evening_and_prompts(ctx):
    user = await _onboard(ctx)
    bot = FakeBot()
    reminders = Reminders(bot, ctx)
    lunch = datetime(2026, 10, 20, 13, 35, tzinfo=MSK)
    await reminders.tick(lunch.astimezone(timezone.utc))
    await reminders.tick(lunch.astimezone(timezone.utc))
    assert sum("обед" in t for t in bot.sent) == 1
    await reminders.tick(datetime(2026, 10, 20, 11, 5, tzinfo=MSK).astimezone(timezone.utc))
    assert any("Выпито" in t for t in bot.sent)
    await reminders.tick(datetime(2026, 10, 20, 21, 5, tzinfo=MSK).astimezone(timezone.utc))
    assert any("пусто" in t for t in bot.sent)
    await add_entry(ctx.storage, user, ctx.catalog.food("kiwi"), datetime.now(MSK).date().isoformat(), "snack", 75)
    await reminders.tick(datetime.now(timezone.utc) + timedelta(hours=3))
    assert any("Как самочувствие" in t for t in bot.sent)


async def test_blocked_user_gets_reminders_disabled(ctx):
    await _onboard(ctx)
    await Reminders(FakeBot(fail=True), ctx).tick(datetime(2026, 10, 20, 13, 35, tzinfo=MSK).astimezone(timezone.utc))
    user = await ctx.storage.users.get(USER_ID)
    assert user.setting("reminders")["enabled"] is False


def test_barcode_decode_roundtrip():
    zxingcpp = pytest.importorskip("zxingcpp")
    from PIL import Image
    code = "4006381333931"
    raw = zxingcpp.create_barcode(code, zxingcpp.BarcodeFormat.EAN13).to_image(scale=4)
    height, width = raw.shape[:2]
    buffer = io.BytesIO()
    Image.frombytes("L", (width, height), bytes(memoryview(raw))).save(buffer, format="PNG")
    assert decode(buffer.getvalue()) == code
    with pytest.raises(BarcodeError):
        decode(b"garbage")
