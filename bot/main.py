import logging
import sys
import os
import asyncio

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "backend"))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from bot.handlers import accounts, budgets, debts, goals, menu, photo, start, subscriptions, transaction
from bot.middlewares.user_middleware import UserMiddleware

logger = logging.getLogger(__name__)

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN or "0:placeholder",
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())
dp.update.middleware(UserMiddleware())

# Порядок важливий: FSM-хендлери реєструються ДО вільного тексту
dp.include_router(start.router)
dp.include_router(accounts.router)
dp.include_router(goals.router)
dp.include_router(debts.router)
dp.include_router(budgets.router)
dp.include_router(subscriptions.router)
dp.include_router(menu.router)
dp.include_router(transaction.router)
dp.include_router(photo.router)

WEBHOOK_PATH = "/bot/webhook"


# ── Webhook-режим (для FastAPI-сервісу з BOT_EMBEDDED=true) ──────────────────

def setup_webhook_routes(app: FastAPI) -> None:
    """Реєструє webhook endpoint у спільному FastAPI-застосунку."""

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(request: Request) -> JSONResponse:
        from aiogram.types import Update
        try:
            # model_validate_json коректно резолвить аліаси ("from" → from_user)
            # і не потребує подвійного JSON-парсингу
            body = await request.body()
            update = Update.model_validate_json(body)
            await dp.feed_update(bot, update)
        except Exception as exc:
            logger.error("Webhook processing error: %s", exc, exc_info=True)
        # Завжди повертаємо 200 — інакше Telegram перестає надсилати апдейти
        return JSONResponse({"ok": True})


async def bot_startup() -> None:
    """Викликається з lifespan FastAPI при старті."""
    from bot.scheduler import setup_scheduler
    setup_scheduler(bot).start()
    if settings.WEBHOOK_URL:
        url = f"{settings.WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
        await bot.set_webhook(url, drop_pending_updates=True, allowed_updates=dp.resolve_used_update_types())
        info = await bot.get_webhook_info()
        logger.info("Webhook встановлено: %s (pending=%s)", info.url, info.pending_update_count)
    else:
        logger.warning("WEBHOOK_URL не вказано — webhook не встановлено.")


async def bot_shutdown() -> None:
    """Викликається з lifespan FastAPI при зупинці."""
    await bot.delete_webhook()
    await bot.session.close()


# ── Standalone webhook-режим (Railway bot-сервіс + WEBHOOK_URL) ──────────────

async def run_webhook() -> None:
    """
    Запуск бота як окремого webhook-сервера.
    Використовується коли bot/main.py запускається самостійно і є WEBHOOK_URL.
    Railway надає $PORT для публічного доступу.
    """
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from app.database import init_db
    from bot.scheduler import setup_scheduler

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Ініціалізація БД (webhook-режим)...")
    await init_db()

    sched = setup_scheduler(bot)
    sched.start()

    webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(webhook_url)
    logger.info("Webhook встановлено: %s", webhook_url)

    aio_app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(aio_app, path=WEBHOOK_PATH)
    setup_application(aio_app, dp, bot=bot)

    port = int(os.environ.get("PORT", "8080"))
    runner = web.AppRunner(aio_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info("Бот запущено (webhook) на порту %d", port)

    try:
        await asyncio.Event().wait()  # блокуємо до зупинки
    finally:
        await bot.delete_webhook()
        sched.shutdown(wait=False)
        await runner.cleanup()
        await bot.session.close()


# ── Polling-режим (локальна розробка) ────────────────────────────────────────

async def run_polling() -> None:
    from app.database import init_db
    from bot.scheduler import setup_scheduler

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Ініціалізація БД...")
    await init_db()
    sched = setup_scheduler(bot)
    sched.start()
    logger.info("Запуск бота @%s в режимі polling...", (await bot.get_me()).username)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        sched.shutdown(wait=False)


# ── Точка входу ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if settings.WEBHOOK_URL:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())
