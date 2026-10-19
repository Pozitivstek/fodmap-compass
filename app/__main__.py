"""Точка входа: API + мини-приложение (uvicorn), бот (long polling) и напоминания в одном процессе."""

from __future__ import annotations

import asyncio
import logging
import signal

import uvicorn

from app.api import create_app
from app.api.deps import AppContext
from app.config import load_settings
from app.db import connect
from app.services.catalog import Catalog
from app.services.foodview import FoodResolver
from app.services.off import OpenFoodFacts
from app.storage import Storage

log = logging.getLogger("fodmap")


async def build_context() -> AppContext:
    settings = load_settings()
    storage = Storage.create(await connect(settings.db_path))
    catalog = Catalog.from_dir(settings.data_dir)
    off = OpenFoodFacts(storage.extras, settings.off_user_agent)
    return AppContext(settings=settings, storage=storage, catalog=catalog, off=off,
                      resolver=FoodResolver(catalog, off, storage.extras))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)
    ctx = await build_context()
    settings = ctx.settings
    log.info("catalog: %d foods, %d recipes", len(ctx.catalog.foods), len(ctx.catalog.recipes))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    tasks = []
    bot = None
    if settings.bot_enabled:
        from app.bot import build_bot, configure
        from app.bot.reminders import Reminders

        bot, dispatcher = build_bot(ctx)
        try:
            await configure(bot, settings.webapp_url)
        except Exception:
            log.exception("bot configure failed (продолжаю без кнопки меню)")
        tasks.append(asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False)))
        if settings.reminders_enabled:
            tasks.append(asyncio.create_task(Reminders(bot, ctx).run(stop)))
    else:
        log.warning("BOT_TOKEN не задан — работает только API")

    server = uvicorn.Server(uvicorn.Config(create_app(ctx), host=settings.host, port=settings.port,
                                           log_level="info", proxy_headers=True, forwarded_allow_ips="*"))
    server.install_signal_handlers = lambda: None
    tasks.append(asyncio.create_task(server.serve()))
    await stop.wait()
    log.info("shutting down")
    server.should_exit = True
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    if bot:
        await bot.session.close()
    await ctx.off.close()
    await ctx.storage.conn.close()


if __name__ == "__main__":
    asyncio.run(main())
