"""Скидання всіх даних користувача.

Двокрокове підтвердження: попередження про наслідки → остаточне «так».
Саме скидання виконує backend-сервіс reset_all_data() в одній транзакції —
бот викликає його напряму зі своєю сесією БД, як і решта хендлерів.
"""
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.database import AsyncSessionLocal
from app.models import User
from app.services.reset_service import reset_all_data

from bot.keyboards.inline import (
    back_keyboard, reset_confirm_keyboard, reset_final_keyboard, settings_menu_keyboard,
)

logger = logging.getLogger(__name__)
router = Router()


def _is_owner(callback: CallbackQuery, db_user: User | None) -> bool:
    """Кнопку натиснув саме той користувач, чиї дані будуть скинуті."""
    return (
        db_user is not None
        and callback.from_user is not None
        and callback.from_user.id == db_user.telegram_id
    )


def _clear_pending_monobank(user_id: int) -> int:
    """Прибирає з памʼяті непідтверджені операції Monobank цього користувача.

    Інакше після скидання лишились би кнопки підтвердження, що посилаються
    на вже видалені рахунки/категорії.
    """
    from bot.handlers import monobank

    pending = getattr(monobank, "_pending", None)
    if not isinstance(pending, dict):
        return 0
    stale = [pid for pid, p in pending.items() if p.get("user_id") == user_id]
    for pid in stale:
        pending.pop(pid, None)
    return len(stale)


# ── Крок 1: попередження ──────────────────────────────────────────────────────

@router.callback_query(F.data == "reset:start")
async def reset_start(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback, db_user):
        await callback.answer("Дія недоступна", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "⚠️ <b>Скидання всіх даних</b>\n\n"
        "Буде видалено <b>НАЗАВЖДИ</b>:\n"
        "• Усі транзакції та перекази\n"
        "• Усі цілі, борги, бюджети\n"
        "• Підключення Monobank (доведеться підключати заново)\n\n"
        "Рахунки та категорії залишаться, але баланси обнуляться до 0.\n\n"
        "Це незворотна дія.",
        reply_markup=reset_confirm_keyboard(),
    )
    await callback.answer()


# ── Крок 2: остаточне підтвердження ───────────────────────────────────────────

@router.callback_query(F.data == "reset:confirm")
async def reset_confirm(callback: CallbackQuery, db_user: User) -> None:
    if not _is_owner(callback, db_user):
        await callback.answer("Дія недоступна", show_alert=True)
        return
    await callback.message.edit_text(
        "⚠️ <b>Ти впевнений?</b> Це видалить ВСЮ історію без можливості відновлення.",
        reply_markup=reset_final_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:cancel")
async def reset_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Скасовано. Дані на місці.", reply_markup=settings_menu_keyboard())
    await callback.answer()


# ── Крок 3: виконання ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "reset:do")
async def reset_execute(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback, db_user):
        await callback.answer("Дія недоступна", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text("⏳ Скидаю дані...")

    try:
        async with AsyncSessionLocal() as db:
            summary = await reset_all_data(db_user.id, db)
    except Exception as e:
        logger.error("Скидання даних не вдалось (user_id=%s): %s", db_user.id, e, exc_info=True)
        await callback.message.edit_text(
            "❌ <b>Не вдалось скинути дані.</b>\n\n"
            "Нічого не змінено — усі дані на місці. Спробуй ще раз пізніше.",
            reply_markup=back_keyboard("menu:settings"),
        )
        return

    _clear_pending_monobank(db_user.id)
    await state.clear()

    await callback.message.edit_text(
        "✅ <b>Дані скинуто.</b>\n\n"
        f"Видалено: {summary['transactions']} транзакцій, "
        f"{summary['transfers']} переказів, "
        f"{summary['goals']} цілей, "
        f"{summary['debts']} боргів, "
        f"{summary['budgets']} бюджетів. "
        "Monobank відключено. "
        f"Баланси {summary['accounts_reset']} рахунків обнулено.",
        reply_markup=back_keyboard("menu:main"),
    )
