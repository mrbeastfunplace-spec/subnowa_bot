from __future__ import annotations

import asyncio
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError

from admin import build_admin_router
from config import load_settings
from db.bootstrap import initialize_database
from db.session import create_engine_and_session
from handlers import build_catalog_router, build_profile_router, build_start_router
from services.capcut import run_capcut_cleanup_loop
from services.context import AppContext


async def main() -> None:
    settings = load_settings()
    engine, session_factory = create_engine_and_session(settings.database_url)
    await initialize_database(engine, session_factory, settings)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    app = AppContext(settings=settings, session_factory=session_factory)
    cleanup_task = asyncio.create_task(run_capcut_cleanup_loop(session_factory))

    dp.include_router(build_admin_router(app, bot))
    dp.include_router(build_catalog_router(app, bot))
    dp.include_router(build_profile_router(app))
    dp.include_router(build_start_router(app, bot))

    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    except TelegramConflictError:
        print("Polling conflict: another bot instance is already using getUpdates.")
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        await bot.session.close()
        await engine.dispose()


def run() -> None:
    asyncio.run(main())
