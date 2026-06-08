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

from app.config import settings
from advisor_bot.handlers import chat
from bot.middlewares.user_middleware import UserMiddleware

logger = logging.getLogger(__name__)

bot = Bot(
    token=settings.ADVISOR_BOT_TOKEN or "0:placeholder",
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())
dp.update.middleware(UserMiddleware())
dp.include_router(chat.router)


async def run_polling() -> None:
    from app.database import init_db

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not settings.ADVISOR_BOT_TOKEN:
        logger.error("ADVISOR_BOT_TOKEN не вказано — Money Deck Advisor не може запуститись.")
        return

    logger.info("Ініціалізація БД...")
    await init_db()
    logger.info("Запуск Money Deck Advisor @%s в режимі polling...", (await bot.get_me()).username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_polling())
