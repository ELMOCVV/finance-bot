import logging

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.config import settings
from app.models import User
from bot.handlers.monobank import clear_pending_for_user
from bot.keyboards.inline import reset_step1_keyboard, reset_step2_keyboard, back_keyboard

logger = logging.getLogger(__name__)
router = Router()

_STEP1_TEXT = (
    "⚠️ <b>Скидання всіх даних</b>\n\n"
    "Буде видалено <b>НАЗАВЖДИ</b>:\n"
    "• Усі транзакції та перекази\n"
    "• Усі цілі, борги, бюджети\n"
    "• Підключення Monobank (доведеться підключати заново)\n\n"
    "Рахунки та категорії залишаться, але баланси обнуляться до 0.\n\n"
    "Це незворотна дія."
)

_STEP2_TEXT = (
    "⚠️ <b>Ти впевнений?</b>\n\n"
    "Це видалить ВСЮ історію без можливості відновлення."
)


@router.callback_query(F.data == "reset:start")
async def reset_start(callback: CallbackQuery, db_user: User) -> None:
    await callback.message.edit_text(_STEP1_TEXT, reply_markup=reset_step1_keyboard())
    await callback.answer()


@router.callback_query(F.data == "reset:step2")
async def reset_step2(callback: CallbackQuery, db_user: User) -> None:
    await callback.message.edit_text(_STEP2_TEXT, reply_markup=reset_step2_keyboard())
    await callback.answer()


@router.callback_query(F.data == "reset:confirm")
async def reset_confirm(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer("Скидаю…")
    url = settings.BACKEND_URL.rstrip("/") + f"/api/v1/users/{db_user.id}/reset-all-data"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url)
        if resp.status_code >= 400:
            raise RuntimeError(f"status {resp.status_code}: {resp.text[:200]}")
        s = resp.json()
    except Exception as e:
        logger.error("Reset failed for user=%s: %s", db_user.id, e)
        await callback.message.edit_text(
            "❌ Не вдалося скинути дані. Нічого не змінено — спробуй трохи пізніше.",
            reply_markup=back_keyboard("menu:settings"),
        )
        return

    # Прибираємо застарілі in-memory Monobank-підтвердження цього юзера.
    clear_pending_for_user(db_user.id)

    await callback.message.edit_text(
        "✅ <b>Дані скинуто.</b>\n\n"
        f"Видалено: {s['transactions']} транзакцій, {s['transfers']} переказів, "
        f"{s['goals']} цілей, {s['debts']} боргів, {s['budgets']} бюджетів. "
        f"Monobank відключено. Баланси {s['accounts_zeroed']} рахунків обнулено.",
        reply_markup=back_keyboard("menu:settings"),
    )
