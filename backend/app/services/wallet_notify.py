"""Неблокуюче надсилання повідомлень бота про витрати з Wallet.

Webhook лише ставить задачу в event loop і одразу відповідає. Будь-яка
помилка Telegram логуються тут і не впливає на вже збережену витрату.
Логіка повідомлень живе в bot.handlers.wallet (лінивий імпорт — як у
Monobank webhook, щоб уникнути циклічних імпортів і працювати без бота).
"""
import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Посилання на задачі, щоб їх не зібрав GC до завершення
_tasks: set[asyncio.Task] = set()


def _owner_tg_id() -> int | None:
    try:
        return int(settings.WALLET_OWNER_TG_ID)
    except ValueError:
        return None


async def _run(kind: str, obj_id: int) -> None:
    try:
        from bot.handlers.wallet import send_wallet_tx_message, send_wallet_pending_message
        chat_id = _owner_tg_id()
        if kind == "tx":
            await send_wallet_tx_message(chat_id, obj_id)
        else:
            await send_wallet_pending_message(chat_id, obj_id)
    except Exception as e:
        logger.error("Wallet notify failed (%s id=%s): %s", kind, obj_id, e, exc_info=True)


def notify_in_background(kind: str, obj_id: int) -> None:
    """kind: "tx" (збережена витрата) | "pending" (відкладена, немає рахунків)."""
    if not settings.TELEGRAM_BOT_TOKEN or _owner_tg_id() is None:
        logger.info("Wallet notify skipped: bot token or owner id not configured")
        return
    task = asyncio.create_task(_run(kind, obj_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def drain() -> None:
    """Дочекатися всіх надсилань (для тестів)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
