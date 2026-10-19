"""Создание бота и диспетчера aiogram."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.api.deps import AppContext
from app.bot.handlers import build_router, send_report

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="app", description="Открыть приложение"),
    BotCommand(command="today", description="Сводка за сегодня"),
    BotCommand(command="report", description="PDF-отчёт для врача"),
    BotCommand(command="help", description="Что умеет бот"),
]


def build_bot(ctx: AppContext) -> tuple[Bot, Dispatcher]:
    bot = Bot(ctx.settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(ctx))

    async def send_document(chat_id: int, pdf: bytes, filename: str, caption: str) -> None:
        await send_report(bot, chat_id, pdf, filename, caption)

    ctx.send_document = send_document
    return bot, dispatcher


async def configure(bot: Bot, webapp_url: str) -> None:
    """Команды и кнопка меню «Открыть» рядом с полем ввода."""
    await bot.set_my_commands(COMMANDS)
    if webapp_url.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="ФудКомпас", web_app=WebAppInfo(url=webapp_url)))
    else:
        log.warning("WEBAPP_URL не https — кнопку меню мини-приложения не ставлю")
