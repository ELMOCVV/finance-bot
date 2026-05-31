from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Goal
from bot.keyboards.inline import goals_keyboard, goal_view_keyboard, confirm_delete_keyboard, skip_keyboard, back_keyboard
from bot.states import AddGoal
from bot.utils.date_utils import fmt_date, parse_date, DATE_HINT

router = Router()


async def _show_goals(target, db_user: User) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Goal).where(Goal.user_id == db_user.id).order_by(Goal.deadline))
        goals = result.scalars().all()

    text = "🎯 <b>Ваші фінансові цілі:</b>" if goals else "🎯 <b>Цілей поки немає.</b>\nДодайте першу:"
    kb = goals_keyboard(goals)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:goals")
async def show_goals(callback: CallbackQuery, db_user: User) -> None:
    await _show_goals(callback, db_user)


# ── Додавання ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "goal:add")
async def start_add_goal(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddGoal.waiting_name)
    await callback.message.edit_text(
        "🎯 <b>Нова ціль</b>\n\nВведіть назву цілі:\n"
        "<i>Наприклад: MacBook Pro, Відпустка в Туреччині</i>",
        reply_markup=back_keyboard("menu:goals"),
    )
    await callback.answer()


@router.message(AddGoal.waiting_name)
async def goal_get_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 256:
        await message.answer("Введіть коректну назву (до 256 символів):")
        return
    await state.update_data(goal_name=name)
    await state.set_state(AddGoal.waiting_amount)
    await message.answer(f"💰 Ціль: <b>{name}</b>\n\nВведіть цільову суму:")


@router.message(AddGoal.waiting_amount)
async def goal_get_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await message.answer("Введіть коректне число більше 0:")
        return
    await state.update_data(goal_amount=amount)
    await state.set_state(AddGoal.waiting_deadline)
    await message.answer(
        f"📅 Введіть дату дедлайну у форматі <b>{DATE_HINT}</b>\n<i>або пропустіть:</i>",
        reply_markup=skip_keyboard("goal:skip_deadline", "cancel:goal"),
    )


@router.callback_query(F.data == "goal:skip_deadline")
async def goal_skip_deadline(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await _save_goal(callback, state, db_user, deadline=None)


@router.message(AddGoal.waiting_deadline)
async def goal_get_deadline(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        deadline = parse_date((message.text or "").strip())
    except ValueError:
        await message.answer(f"Невірний формат. Введіть дату {DATE_HINT} або натисніть «Пропустити»:")
        return
    await _save_goal(message, state, db_user, deadline=deadline)


async def _save_goal(target, state: FSMContext, db_user: User, deadline) -> None:
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        goal = Goal(
            user_id=db_user.id,
            name=data["goal_name"],
            target_amount=data["goal_amount"],
            current_amount=0.0,
            currency="UAH",
            deadline=deadline,
        )
        db.add(goal)
        await db.commit()
    await state.clear()
    text = f"✅ Ціль «<b>{data['goal_name']}</b>» додано!"
    if isinstance(target, CallbackQuery):
        await target.answer(text, show_alert=True)
    else:
        await target.answer(text)
    await _show_goals(target, db_user)


@router.callback_query(F.data == "cancel:goal")
async def cancel_goal(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await _show_goals(callback, db_user)


# ── Перегляд ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goal:view:"))
async def view_goal(callback: CallbackQuery, db_user: User) -> None:
    goal_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == db_user.id))
        )
        g = result.scalar_one_or_none()

    if not g:
        await callback.answer("Ціль не знайдено")
        return

    filled = round(g.progress_percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    deadline_str = f"\n📅 Дедлайн: {fmt_date(g.deadline)}" if g.deadline else ""
    await callback.message.edit_text(
        f"🎯 <b>{g.name}</b>\n\n"
        f"[{bar}] {g.progress_percent:.1f}%\n"
        f"💰 {g.current_amount:.0f} / {g.target_amount:.0f} {g.currency}"
        f"{deadline_str}",
        reply_markup=goal_view_keyboard(goal_id),
    )
    await callback.answer()


# ── Видалення ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("goal:del_confirm:"))
async def goal_del_confirm(callback: CallbackQuery, db_user: User) -> None:
    goal_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == db_user.id))
        )
        g = result.scalar_one_or_none()
    name = g.name if g else f"#{goal_id}"
    await callback.message.edit_text(
        f"⚠️ Видалити ціль «<b>{name}</b>»?\n\nЦе незворотньо.",
        reply_markup=confirm_delete_keyboard(
            confirm_cb=f"goal:delete:{goal_id}",
            cancel_cb=f"goal:view:{goal_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("goal:delete:"))
async def goal_delete(callback: CallbackQuery, db_user: User) -> None:
    goal_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == db_user.id))
        )
        goal = result.scalar_one_or_none()
        if goal:
            await db.delete(goal)
            await db.commit()
    await callback.answer("✅ Ціль видалено")
    await _show_goals(callback, db_user)
