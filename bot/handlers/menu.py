from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.database import AsyncSessionLocal
from app.models import User
from app.services.analytics_service import analytics_service
from app.services.exchange_rate_service import exchange_rate_service
from bot.keyboards.inline import back_keyboard, currency_flag, main_menu_keyboard, settings_menu_keyboard
from bot.states import AddTransaction

router = Router()


@router.callback_query(F.data == "menu:main")
async def show_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:analytics")
async def show_analytics(callback: CallbackQuery, db_user: User) -> None:
    month = datetime.utcnow().strftime("%Y-%m")
    async with AsyncSessionLocal() as db:
        summary = await analytics_service.get_summary(db, db_user.id, month)
    cats = []
    async with AsyncSessionLocal() as db:
        cats = await analytics_service.get_expenses_by_category(db, db_user.id, month)

    lines = [
        f"📊 <b>Аналитика за {month}:</b>\n",
        f"➕ Доходы: <b>{summary['total_income_uah']:.2f} ₴</b>",
        f"➖ Расходы: <b>{summary['total_expense_uah']:.2f} ₴</b>",
        f"💰 Результат: <b>{summary['net_uah']:.2f} ₴</b>",
    ]
    if cats:
        lines.append("\n<b>Топ расходов:</b>")
        for c in cats[:5]:
            lines.append(f"  {c['icon']} {c['name']}: {c['total_uah']:.0f} ₴")

    await callback.message.edit_text("\n".join(lines), reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:transactions")
async def show_recent_transactions(callback: CallbackQuery, db_user: User) -> None:
    from bot.keyboards.inline import transaction_list_keyboard
    from bot.utils.tx_helpers import load_recent_activity

    items = await load_recent_activity(db_user.id, limit=10)

    if not items:
        await callback.message.edit_text(
            "💰 <b>Транзакций ещё нет.</b>",
            reply_markup=back_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "💰 <b>Последние транзакции</b> (нажми для деталей):",
        reply_markup=transaction_list_keyboard(items),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:advisor")
async def show_advisor_promo(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "💼 Твой персональный финансовый ассистент @MoneyDeckAssistantBot\n"
        "Он знает твои финансы и ответит на любой вопрос!",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


# ── Кнопки "Додати витрату" і "Фото чека" ────────────────────────────────────

@router.callback_query(F.data == "menu:add_expense")
async def menu_add_expense(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddTransaction.waiting_text)
    await callback.message.edit_text(
        "💸 <b>Новый расход</b>\n\n"
        "Напиши, что и сколько потратил:\n\n"
        "<i>«Кофе 50 грн», «Продукты 350 UAH», «Такси 120»</i>",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:add_income")
async def menu_add_income(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddTransaction.waiting_income_text)
    await callback.message.edit_text(
        "💰 <b>Новый доход</b>\n\n"
        "Напиши, что и сколько получил:\n\n"
        "<i>«Зарплата 15000», «Фриланс 5000 USD», «Аванс 7500»</i>",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:balance")
async def show_balance(callback: CallbackQuery, db_user: User) -> None:
    from sqlalchemy import select
    from app.models import Account
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = res.scalars().all()

    if not accounts:
        await callback.message.edit_text(
            "💼 <b>Счетов ещё нет.</b>\n\nДобавь первый счёт:",
            reply_markup=back_keyboard("menu:accounts"),
        )
        await callback.answer()
        return

    lines = ["💼 <b>Твои счета:</b>\n"]
    total_uah = 0.0
    for acc in accounts:
        flag = currency_flag(acc.currency)
        star = " ⭐" if acc.is_default else ""
        if acc.currency == "UAH":
            uah = acc.balance
            lines.append(f"{flag} {acc.name}{star} — {acc.balance:,.0f} UAH")
        else:
            uah = await exchange_rate_service.to_uah(acc.balance, acc.currency)
            lines.append(
                f"{flag} {acc.name}{star} — {acc.balance:,.2f} {acc.currency}"
                f" (~{uah:,.0f} ₴)"
            )
        total_uah += uah

    lines.append(f"\n💰 <b>Всего: ~{total_uah:,.0f} ₴</b>")
    await callback.message.edit_text("\n".join(lines), reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def show_settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("⚙️ <b>Меню:</b>", reply_markup=settings_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:add_photo")
async def menu_add_photo(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📷 Пришли фото чека, и я его распознаю:",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel:flow")
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Отменено.", reply_markup=back_keyboard())
    await callback.answer()
