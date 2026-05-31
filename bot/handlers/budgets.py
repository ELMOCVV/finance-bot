from datetime import datetime
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Budget, Category
from app.services.analytics_service import analytics_service
from bot.keyboards.inline import (
    budget_list_keyboard, budget_categories_keyboard,
    use_current_month_keyboard, back_keyboard,
)
from bot.states import CreateBudget

router = Router()


def _bar(spent: float, limit: float, length: int = 10) -> str:
    if limit <= 0:
        return "░" * length
    pct = min(spent / limit, 1.0)
    filled = round(pct * length)
    return "█" * filled + "░" * (length - filled)


async def _show_budgets(target, db_user: User, month: str | None = None) -> None:
    if not month:
        month = datetime.utcnow().strftime("%Y-%m")

    async with AsyncSessionLocal() as db:
        budgets = await analytics_service.get_budget_status(db, db_user.id, month)

    if not budgets:
        text = (
            f"📋 <b>Бюджети за {month}</b>\n\n"
            "Бюджетів ще немає. Натисніть «➕ Додати бюджет»:"
        )
    else:
        lines = [f"📋 <b>Бюджети за {month}:</b>"]
        for b_item in budgets:
            pct = round(b_item["spent"] / b_item["limit"] * 100) if b_item["limit"] else 0
            bar = _bar(b_item["spent"], b_item["limit"])
            warn = " ⚠️" if b_item["is_exceeded"] else ""
            status = "🔴" if b_item["is_exceeded"] else "🟢"
            lines.append(
                f"\n{status} {b_item['icon']} <b>{b_item['category']}</b>\n"
                f"   {b_item['spent']:.0f} / {b_item['limit']:.0f} {b_item['currency']} "
                f"[{bar}] {pct}%{warn}"
            )
        text = "\n".join(lines)

    kb = budget_list_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:budgets")
async def show_budgets(callback: CallbackQuery, db_user: User) -> None:
    await _show_budgets(callback, db_user)


# ── Крок 1: вибір категорії ──────────────────────────────────────────────────

@router.callback_query(F.data == "budgets:add")
async def start_add_budget(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category)
            .where(and_(Category.user_id == db_user.id, Category.type == "expense"))
            .order_by(Category.name)
        )
        categories = res.scalars().all()

    if not categories:
        await callback.answer("Спочатку додайте категорії витрат через /start!", show_alert=True)
        return

    await state.set_state(CreateBudget.waiting_category)
    await callback.message.edit_text(
        "📋 <b>Новий бюджет</b>\n\nВиберіть категорію витрат:",
        reply_markup=budget_categories_keyboard(categories),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("bcat:"), CreateBudget.waiting_category)
async def budget_get_category(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    cat_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category).where(and_(Category.id == cat_id, Category.user_id == db_user.id))
        )
        cat = res.scalar_one_or_none()

    if not cat:
        await callback.answer("Категорію не знайдено")
        return

    await state.update_data(budget_cat_id=cat_id, budget_cat_name=cat.name, budget_cat_icon=cat.icon or "")
    await state.set_state(CreateBudget.waiting_amount)
    await callback.message.edit_text(
        f"📋 Бюджет: {cat.icon or ''} <b>{cat.name}</b>\n\n"
        "Введіть ліміт витрат на місяць (UAH):",
        reply_markup=back_keyboard("budgets:add"),
    )
    await callback.answer()


# ── Крок 2: ліміт ────────────────────────────────────────────────────────────

@router.message(CreateBudget.waiting_amount)
async def budget_get_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await message.answer("Введіть коректне число більше 0:")
        return

    await state.update_data(budget_amount=amount)
    await state.set_state(CreateBudget.waiting_month)
    current_month = datetime.utcnow().strftime("%Y-%m")
    await message.answer(
        "📅 Для якого місяця встановити бюджет?\n\n"
        "Введіть у форматі <b>РРРР-ММ</b> або використайте поточний:",
        reply_markup=use_current_month_keyboard(current_month),
    )


# ── Крок 3: місяць ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "budget:cur_month", CreateBudget.waiting_month)
async def budget_use_current_month(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await _save_budget(callback, state, db_user, datetime.utcnow().strftime("%Y-%m"))


@router.message(CreateBudget.waiting_month)
async def budget_get_month(message: Message, state: FSMContext, db_user: User) -> None:
    text = (message.text or "").strip()
    try:
        datetime.strptime(text, "%Y-%m")
    except ValueError:
        await message.answer(
            "Невірний формат. Введіть РРРР-ММ (наприклад: 2026-06)\n"
            "або натисніть «Поточний»:"
        )
        return
    await _save_budget(message, state, db_user, text)


async def _save_budget(target, state: FSMContext, db_user: User, month: str) -> None:
    data = await state.get_data()
    cat_id = data["budget_cat_id"]
    cat_name = data["budget_cat_name"]
    amount = data["budget_amount"]

    async with AsyncSessionLocal() as db:
        existing = await db.execute(
            select(Budget).where(
                and_(
                    Budget.user_id == db_user.id,
                    Budget.category_id == cat_id,
                    Budget.month == month,
                )
            )
        )
        if existing.scalar_one_or_none():
            msg = f"⚠️ Бюджет «{cat_name}» на {month} вже існує!"
            if isinstance(target, CallbackQuery):
                await target.answer(msg, show_alert=True)
            else:
                await target.answer(msg)
            await state.clear()
            return

        db.add(Budget(
            user_id=db_user.id,
            category_id=cat_id,
            month=month,
            limit_amount=amount,
            spent_amount=0.0,
            currency="UAH",
        ))
        await db.commit()

    await state.clear()
    ok_text = f"✅ Бюджет «{cat_name}» на {month} — {amount:.0f} UAH створено!"
    if isinstance(target, CallbackQuery):
        await target.answer(ok_text, show_alert=True)
    else:
        await target.answer(ok_text)
    await _show_budgets(target, db_user, month)
