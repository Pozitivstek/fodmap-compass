"""Фоновые напоминания: вопросы о самочувствии после еды, приёмы пищи, вода, вечерний «огонёк»."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.api.deps import AppContext
from app.bot.texts import app_button, prompt_text, reaction_keyboard
from app.clock import local_now, utcnow
from app.domain import MEALS
from app.services.journal import stats
from app.storage.users import User

log = logging.getLogger(__name__)

TICK_SECONDS = 60
WINDOW = timedelta(minutes=30)
WATER_CHECKS = ((time(11, 0), 0.3), (time(15, 0), 0.55), (time(18, 30), 0.8))
EVENING_AT = time(21, 0)
STALE_PROMPT = timedelta(hours=6)


def in_window(now: datetime, at: time) -> bool:
    start = now.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    return start <= now < start + WINDOW


def _parse(value: str | None) -> time | None:
    try:
        return time.fromisoformat(value) if value else None
    except ValueError:
        return None


WATER_KEYBOARD = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="💧 +250 мл", callback_data="water:250"),
    InlineKeyboardButton(text="💧 +500 мл", callback_data="water:500"),
]])


class Reminders:
    def __init__(self, bot: Bot, ctx: AppContext):
        self._bot, self._ctx = bot, ctx

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick(utcnow())
            except Exception:  # цикл не должен умирать из-за одной ошибки
                log.exception("reminders tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=TICK_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def tick(self, now: datetime) -> None:
        await self._prompts(now)
        for user in await self._ctx.storage.users.all_onboarded():
            settings = user.setting("reminders") or {}
            if not settings.get("enabled"):
                continue
            try:
                await self._for_user(user, settings, local_now(user.tz, now))
            except Exception:  # ошибка у одного пользователя не должна лишать напоминаний остальных
                log.exception("reminders failed for user %s", user.id)
        if now.minute == 0:
            await self._ctx.storage.extras.off_prune()

    async def _send(self, user: User, text: str, markup=None) -> bool:
        try:
            await self._bot.send_message(user.id, text, reply_markup=markup)
            return True
        except TelegramForbiddenError:
            log.info("user %s blocked the bot, reminders off", user.id)
            await self._ctx.storage.users.update(user, {"reminders": {"enabled": False}})
            return False

    async def _prompts(self, now: datetime) -> None:
        storage = self._ctx.storage
        for prompt in await storage.extras.due_prompts(now):
            await storage.extras.mark_prompt(prompt["id"], sent=True)
            user = await storage.users.get(prompt["user_id"])
            due = datetime.fromisoformat(prompt["due_at"])
            if not user or not (user.setting("reminders") or {}).get("enabled") or now - due > STALE_PROMPT:
                continue
            entries = [e for e in await storage.diary.by_day(user.id, prompt["day"]) if e.meal == prompt["meal"]]
            if not entries:
                continue
            url = self._ctx.settings.webapp_url
            try:
                await self._send(user, prompt_text(prompt["meal"], [e.name for e in entries]),
                                 reaction_keyboard(prompt["id"], url, prompt["day"], prompt["meal"]))
            except Exception:
                log.exception("prompt %s failed for user %s", prompt["id"], user.id)

    async def _for_user(self, user: User, settings: dict, now: datetime) -> None:
        storage, day = self._ctx.storage, now.date().isoformat()
        url = self._ctx.settings.webapp_url
        entries = await storage.diary.by_day(user.id, day)
        for meal, value in (settings.get("meals") or {}).items():
            at = _parse(value)
            logged = any(e.meal == meal for e in entries)
            if at and not logged and in_window(now, at) and await storage.extras.remind_once(user.id, f"meal_{meal}", day):
                spec = MEALS.get(meal, MEALS["snack"])
                await self._send(user, f"{spec['emoji']} Время приёма «{spec['name'].lower()}». Не забудьте записать, что съели!",
                                 app_button(url, "➕ Записать", f"/add?meal={meal}"))
        if settings.get("water"):
            await self._water(user, now, day)
        if settings.get("evening") and not entries and in_window(now, EVENING_AT) \
                and await storage.extras.remind_once(user.id, "evening", day):
            current = (await stats(storage, user))["streak"]["current"]
            text = (f"🔥 Ваша серия — {current} дн. Запишите хотя бы один приём пищи, чтобы огонёк не погас!"
                    if current else "🌙 Сегодня в дневнике пусто. Запишите, что ели, — это займёт минуту.")
            await self._send(user, text, app_button(url, "📒 Открыть дневник", "/diary"))

    async def _water(self, user: User, now: datetime, day: str) -> None:
        storage = self._ctx.storage
        goal = int(user.setting("water_goal_ml") or 2000)
        for at, share in WATER_CHECKS:
            if not in_window(now, at):
                continue
            drunk = await storage.extras.water(user.id, day)
            if drunk < goal * share and await storage.extras.remind_once(user.id, f"water_{at.hour}", day):
                await self._send(user, f"💧 Выпито {drunk} из {goal} мл. Самое время для стакана воды.", WATER_KEYBOARD)
