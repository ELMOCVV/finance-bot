import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import transactions, accounts, categories, debts, goals, budgets, analytics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Заповнюється нижче якщо BOT_EMBEDDED=true (до визначення lifespan не потрібне)
_bot_startup = None
_bot_shutdown = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ініціалізація бази даних...")
    await init_db()
    logger.info("База даних готова.")
    if _bot_startup:
        await _bot_startup()
    yield
    if _bot_shutdown:
        await _bot_shutdown()
    logger.info("Завершення роботи API.")


app = FastAPI(
    title="FinanceAI Bot API",
    version="1.0.0",
    description="REST API для фінансового Telegram-бота з AI-підтримкою",
    lifespan=lifespan,
    # Swagger/ReDoc вимикаємо в продакшні якщо потрібно
    docs_url=None if os.getenv("DISABLE_DOCS") else "/docs",
    redoc_url=None if os.getenv("DISABLE_DOCS") else "/redoc",
)

# CORS: в продакшні — тільки дозволені origin з env, в dev — localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутери API
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(accounts.router,     prefix="/api/v1")
app.include_router(categories.router,   prefix="/api/v1")
app.include_router(debts.router,        prefix="/api/v1")
app.include_router(goals.router,        prefix="/api/v1")
app.include_router(budgets.router,      prefix="/api/v1")
app.include_router(analytics.router,    prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "FinanceAI Bot API"}


# Вбудований bot webhook — тільки якщо BOT_EMBEDDED=true
# (коли бот і API в одному Railway-сервісі)
if os.getenv("BOT_EMBEDDED", "false").lower() == "true":
    try:
        from bot.main import setup_webhook_routes, bot_startup, bot_shutdown
        setup_webhook_routes(app)
        _bot_startup = bot_startup
        _bot_shutdown = bot_shutdown
        logger.info("Webhook маршрути бота підключено.")
    except ImportError:
        logger.warning("Модуль бота не знайдено — webhook не підключено.")


# Для локального запуску: python backend/app/main.py
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
