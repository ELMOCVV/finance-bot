"""«🧹 Почати з нуля» — скидання історії й введення стартових балансів.

⚙️ Меню → «🧹 Почати з нуля» → що буде видалено / що лишиться → підтвердження
словом СКИНУТИ → скидання (app.services.reset_service) → бот по черзі питає
поточний баланс кожного рахунку (число або «0») → підсумок.
"""
import html

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database import AsyncSessionLocal
from app.models import Account, User
from app.services.reset_service import preview_reset, reset_user_history
from bot.handlers.wallet import fmt_amount
from bot.states import ResetHistory
from bot.utils.fsm_edit import HOST_MID_KEY, edit_host

router = Router()

CONFIRM_WORD = "СКИНУТИ"


def _cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="reset:cancel"))
    return b.as_markup()


def _menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏠 Головне меню", callback_data="menu:main"))
    return b.as_markup()


@router.callback_query(F.data == "reset:start")
async def reset_start(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    async with AsyncSessionLocal() as db:
        pv = await preview_reset(db, db_user.id)
    await state.clear()
    await state.set_state(ResetHistory.waiting_confirm)
    await state.update_data(**{HOST_MID_KEY: callback.message.message_id})
    accs = ", ".join(html.escape(a.name) for a in pv.accounts) or "—"
    await callback.message.edit_text(
        "🧹 <b>Почати з нуля</b>\n\n"
        f"<b>Буде видалено:</b> {pv.transactions} транзакцій (витрати й доходи) і {pv.transfers} переказів.\n"
        "<b>Обнулиться:</b> баланси рахунків, «витрачено» в бюджетах, накопичене в цілях.\n"
        f"<b>Лишиться:</b> рахунки ({accs}), категорії, ліміти бюджетів, цілі, борги, підписки, "
        "картки Wallet і Monobank.\n\n"
        "Потім я спитаю, скільки зараз грошей на кожному рахунку.\n\n"
        f"⚠️ Це не можна скасувати. Щоб підтвердити, напиши <b>{CONFIRM_WORD}</b>.",
        reply_markup=_cancel_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "reset:cancel")
async def reset_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Скасовано — нічого не змінено.", reply_markup=_menu_kb())
    await callback.answer()


@router.message(ResetHistory.waiting_confirm)
async def reset_confirm(message: Message, db_user: User, state: FSMContext) -> None:
    if (message.text or "").strip().upper() != CONFIRM_WORD:
        await edit_host(message, state, "Не підтверджено — нічого не змінено.", _menu_kb())
        await state.clear()
        return
    async with AsyncSessionLocal() as db:
        user = await db.get(User, db_user.id)
        await reset_user_history(db, user)
        await db.commit()
        pv = await preview_reset(db, db_user.id)
    from bot.handlers.monobank import drop_user_pending
    drop_user_pending(db_user.id)
    if not pv.accounts:
        await edit_host(message, state, "✅ Історію скинуто. Рахунків немає — створи їх у ⚙️ Меню → 🏦 Рахунки.", _menu_kb())
        await state.clear()
        return
    await state.set_state(ResetHistory.waiting_balance)
    await state.update_data(r_queue=[a.id for a in pv.accounts], r_done=[])
    await _ask_next(message, state)


async def _ask_next(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        acc = await db.get(Account, data["r_queue"][0])
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="0", callback_data="reset:zero"))
    left = len(data["r_queue"])
    await edit_host(
        message, state,
        f"✅ Історію скинуто.\n\n🏦 <b>{html.escape(acc.name)}</b> ({acc.currency})"
        f"{f' · ще {left - 1}' if left > 1 else ''}\n"
        f"Скільки зараз грошей на цьому рахунку? Напиши число, напр. <i>12500</i> або <i>350,75</i>:",
        b.as_markup(),
    )


async def _set_balance(message: Message, state: FSMContext, balance: float) -> None:
    data = await state.get_data()
    queue, done = list(data["r_queue"]), list(data["r_done"])
    async with AsyncSessionLocal() as db:
        acc = await db.get(Account, queue.pop(0))
        acc.balance = balance
        await db.commit()
        done.append(f"• {html.escape(acc.name)}: <b>{fmt_amount(balance, acc.currency)}</b>")
    if queue:
        await state.update_data(r_queue=queue, r_done=done)
        await _ask_next(message, state)
        return
    await edit_host(message, state, "🚀 <b>Старт!</b> Поточні баланси:\n" + "\n".join(done), _menu_kb())
    await state.clear()


@router.message(ResetHistory.waiting_balance)
async def reset_balance(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        balance = float(raw)
    except ValueError:
        await message.answer("Введи число, наприклад <i>12500</i> або <i>350,75</i>:")
        return
    await _set_balance(message, state, balance)


@router.callback_query(F.data == "reset:zero", ResetHistory.waiting_balance)
async def reset_zero(callback: CallbackQuery, state: FSMContext) -> None:
    await _set_balance(callback.message, state, 0.0)
    await callback.answer()
