"""Обработчики команд, сообщений и кнопок бота."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.api.deps import AppContext
from app.bot.texts import HELP, LEVEL_EMOJI, WELCOME, app_button, food_text
from app.domain import FEELINGS, MEALS
from app.services import fodmap
from app.services.barcode import BarcodeError, decode_async
from app.services.foodview import to_tolerance
from app.services.journal import day_summary, record_reaction, report_pdf, stats, today_for
from app.services.off import OffUnavailable, to_food
from app.services.report import ReportError

log = logging.getLogger(__name__)
MAX_QUERY = 60
MAX_RESULTS = 3
REPORT_DAYS = 30


def build_router(ctx: AppContext) -> Router:
    router = Router(name="main")
    url = ctx.settings.webapp_url

    async def _user(message_or_call):
        tg = message_or_call.from_user
        return await ctx.storage.users.ensure(tg.id, tg.first_name or "", tg.username or "")

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        user = await _user(message)
        await message.answer(WELCOME.format(name=escape(user.first_name or "друг")), reply_markup=app_button(url))

    @router.message(Command("help"))
    async def help_(message: Message) -> None:
        await message.answer(HELP)

    @router.message(Command("app"))
    async def open_app(message: Message) -> None:
        await message.answer("Ваш дневник и справочник:", reply_markup=app_button(url))

    @router.message(Command("today"))
    async def today(message: Message) -> None:
        user = await _user(message)
        summary = await day_summary(ctx.storage, user, today_for(user))
        progress = await stats(ctx.storage, user)
        total, target = summary["totals"], summary["targets"]
        lines = [f"🔥 Серия: <b>{progress['streak']['current']}</b> дн.",
                 f"🍽 {total['kcal']:g} из {target['kcal']} ккал · Б {total['protein']:g} · Ж {total['fat']:g} · "
                 f"У {total['carbs']:g}", f"💧 Вода: {summary['water']['ml']} из {summary['water']['goal']} мл"]
        for meal in summary["meals"].values():
            if meal["entries"]:
                names = ", ".join(escape(e["name"]) for e in meal["entries"])
                lines.append(f"{meal['emoji']} {meal['name']}: {names}")
        lines.append(f"{LEVEL_EMOJI[summary['stack']['level']]} {summary['stack']['message']}")
        await message.answer("\n".join(lines), reply_markup=app_button(url, "📒 Открыть дневник", "/diary"))

    @router.message(Command("report"))
    async def report(message: Message) -> None:
        user = await _user(message)
        if not ctx.limiters["report"].allow(f"report:{user.id}"):
            await message.answer("Отчёт уже недавно собирался, попробуйте через 10 минут.")
            return
        try:
            pdf, filename, period = await report_pdf(ctx.storage, user, REPORT_DAYS)
        except ReportError:
            log.exception("report failed for %s", user.id)
            await message.answer("Не получилось собрать PDF, попробуйте позже.")
            return
        await message.answer_document(BufferedInputFile(pdf, filename=filename),
                                      caption=f"📄 Отчёт за {period}. Его можно переслать врачу.")

    @router.message(F.photo)
    async def photo(message: Message, bot: Bot) -> None:
        user = await _user(message)
        file = await bot.download(message.photo[-1])
        try:
            code = await decode_async(file.read())
        except BarcodeError as exc:
            await message.answer(str(exc))
            return
        if not code:
            await message.answer("Не вижу штрихкода. Сфотографируйте ближе и ровнее или пришлите цифры.")
            return
        await _answer_barcode(message, user, code)

    async def _answer_barcode(message: Message, user, code: str) -> None:
        try:
            product = await ctx.off.product(code)
        except OffUnavailable:
            await message.answer("Open Food Facts сейчас не отвечает, попробуйте чуть позже.")
            return
        if not product:
            await message.answer(f"Товар {code} пока не внесён в Open Food Facts. Проверьте состав на упаковке.")
            return
        await ctx.storage.users.bump_stat(user, "scans")
        food = to_food(product, ctx.catalog)
        verdict = fodmap.evaluate(food, fodmap.Profile.from_settings(user.data),
                                  tolerance=to_tolerance(await ctx.storage.tolerances.get(user.id, food.ref)))
        await message.answer(food_text(food, verdict), reply_markup=app_button(url, "Подробнее", f"/food/{food.ref}"))

    @router.message(F.text & ~F.text.startswith("/"))
    async def lookup(message: Message) -> None:
        user = await _user(message)
        query = message.text.strip()[:MAX_QUERY]
        digits = query.replace(" ", "")
        if digits.isdigit() and 8 <= len(digits) <= 14:
            await _answer_barcode(message, user, digits)
            return
        cleaned = query.lower().removeprefix("можно ли").strip(" ?!.")
        found = ctx.catalog.search(cleaned, limit=MAX_RESULTS)
        if not found:
            await message.answer("Не нашёл в справочнике. Поищите в приложении — там есть товары из магазинов.",
                                 reply_markup=app_button(url, "🔍 Искать в приложении", f"/foods?q={cleaned}"))
            return
        profile = fodmap.Profile.from_settings(user.data)
        tolerances = await ctx.storage.tolerances.all(user.id)
        food = found[0]
        verdict = fodmap.evaluate(food, profile, tolerance=to_tolerance(tolerances.get(food.ref)))
        text = food_text(food, verdict)
        if len(found) > 1:
            text += "\n\nЕщё похожие: " + ", ".join(escape(f.name) for f in found[1:])
        await message.answer(text, reply_markup=app_button(url, "Открыть карточку", f"/food/{food.ref}"))

    @router.callback_query(F.data.startswith("rx:"))
    async def reaction(call: CallbackQuery) -> None:
        _, prompt_id, feeling = call.data.split(":", 2)
        prompt = await ctx.storage.extras.prompt(int(prompt_id)) if prompt_id.isdigit() else None
        if not prompt or prompt["user_id"] != call.from_user.id or feeling not in FEELINGS:
            await call.answer("Этот вопрос уже неактуален")
            return
        if prompt["answered"]:
            await call.answer("Уже записано — спасибо!")
            return
        # Помечаем сразу, чтобы двойное нажатие не записало реакцию дважды.
        await ctx.storage.extras.mark_prompt(int(prompt_id), answered=True)
        user = await _user(call)
        result = await record_reaction(ctx.storage, user, day=prompt["day"], meal=prompt["meal"], ref=None,
                                       feeling=feeling, symptoms=[], severity=0, note="")
        spec = FEELINGS[feeling]
        meal = MEALS[prompt["meal"]]["name"].lower()
        text = f"{spec['emoji']} Записал: «{spec['name']}» после приёма «{meal}»."
        if result["updated"]:
            text += f"\nОтметки обновлены у продуктов: {len(result['updated'])}."
        markup = None
        if spec["weight"] > 0:
            text += "\nЕсли хотите, укажите симптомы — так анализ будет точнее."
            markup = app_button(url, "✍️ Указать симптомы", f"/react?day={prompt['day']}&meal={prompt['meal']}")
        await call.message.edit_text(text, reply_markup=markup)
        await call.answer("Сохранено")

    @router.callback_query(F.data.startswith("water:"))
    async def water(call: CallbackQuery) -> None:
        user = await _user(call)
        amount = call.data.split(":", 1)[1]
        delta = int(amount) if amount.isdigit() and int(amount) <= 1000 else 250
        total = await ctx.storage.extras.add_water(user.id, today_for(user), delta)
        await call.answer(f"💧 +{delta} мл, всего {total} мл")

    return router


async def send_report(bot: Bot, chat_id: int, pdf: bytes, filename: str, caption: str) -> None:
    await bot.send_document(chat_id, BufferedInputFile(pdf, filename=filename), caption=caption)
