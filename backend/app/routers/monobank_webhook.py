"""Webhook Monobank.

GET  /webhooks/monobank/{connection_id} — Monobank перевіряє URL при
     реєстрації, очікуючи 200.
POST /webhooks/monobank/{connection_id} — вхідна StatementItem-подія:
     звіряємо картку за mono_account_id, категоризуємо та надсилаємо
     користувачу повідомлення-підтвердження з inline-кнопками.

Обробка передається в bot.handlers.monobank (лінивий імпорт, щоб уникнути
циклічної залежності та щоб роутер підключався навіть без бота).
"""
import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/monobank", tags=["monobank"])


@router.get("/{connection_id}")
async def verify_webhook(connection_id: int) -> dict:
    """Підтвердження URL для Monobank."""
    return {"status": "ok"}


@router.post("/{connection_id}")
async def receive_webhook(connection_id: int, request: Request) -> dict:
    """Приймає подію Monobank. Завжди повертає 200, щоб Monobank не ретраїв."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    try:
        data = payload.get("data") or {}
        mono_account_id = data.get("account")
        item = data.get("statementItem")
        if mono_account_id and isinstance(item, dict):
            # Лінивий імпорт: логіка підтвердження живе в бот-хендлері
            from bot.handlers.monobank import handle_webhook_statement
            await handle_webhook_statement(connection_id, mono_account_id, item)
    except Exception as e:
        logger.error("Monobank webhook processing error: %s", e, exc_info=True)

    return {"status": "ok"}
