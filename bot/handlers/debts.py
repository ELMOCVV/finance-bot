from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Debt
from bot.keyboards.inline import debts_keyboard, debt_view_keyboard, confirm_delete_keyboard, skip_keyboard, back_keyboard
from bot.states import AddDebt
from bot.utils.date_utils import fmt_date, parse_date, DATE_HINT
from bot.utils.fsm_edit import edit_host, HOST_MID_KEY

router = Router()


async def _show_debts(target, db_user: User, host_mid: int | None = None) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Debt).where(Debt.user_id == db_user.id).order_by(Debt.next_payment_date)
        )
        debts = result.scalars().all()

    text = "💳 <b>Ваші борги:</b>" if debts else "💳 <b>Боргів немає.</b>\nДодайте перший:"
    kb = debts_keyboard(debts)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    elif host_mid:
        try:
            await target.bot.edit_message_text(text, chat_id=target.chat.id, message_id=host_mid, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await target.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:debts")
async def show_debts(callback: CallbackQuery, db_user: User) -> None:
    await _show_debts(callback, db_user)


# ── Додавання ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "debt:add")
async def start_add_debt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddDebt.waiting_name)
    await state.update_data(**{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text(
        "💳 <b>Новий борг</b>\n\nВведіть назву боргу:\n"
        "<i>Наприклад: Іпотека ПриватБанк, Кредит на авто</i>",
        reply_markup=back_keyboard("menu:debts"),
    )
    await callback.answer()


@router.message(AddDebt.waiting_name)
async def debt_get_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 256:
        await edit_host(message, state, "💳 Введіть коректну назву (до 256 символів):", reply_markup=back_keyboard("menu:debts"))
        return
    await state.update_data(debt_name=name)
    await state.set_state(AddDebt.waiting_total)
    await edit_host(message, state, f"💳 Борг: <b>{name}</b>\n\nВведіть загальну суму боргу:")


@router.message(AddDebt.waiting_total)
async def debt_get_total(message: Message, state: FSMContext) -> None:
    try:
        total = float((message.text or "").replace(",", ".").strip())
        assert total > 0
    except (ValueError, AssertionError):
        await edit_host(message, state, "💳 Введіть коректне число більше 0:")
        return
    await state.update_data(debt_total=total, debt_remaining=total)
    await state.set_state(AddDebt.waiting_monthly)
    await edit_host(message, state, "💸 Щомісячний платіж (введіть 0 якщо невідомо):")


@router.message(AddDebt.waiting_monthly)
async def debt_get_monthly(message: Message, state: FSMContext) -> None:
    try:
        monthly = float((message.text or "").replace(",", ".").strip())
        assert monthly >= 0
    except (ValueError, AssertionError):
        await edit_host(message, state, "💸 Введіть число ≥ 0:")
        return
    await state.update_data(debt_monthly=monthly)
    await state.set_state(AddDebt.waiting_rate)
    await edit_host(message, state, "📊 Відсоткова ставка річна % (введіть 0 якщо немає):")


@router.message(AddDebt.waiting_rate)
async def debt_get_rate(message: Message, state: FSMContext) -> None:
    try:
        rate = float((message.text or "").replace(",", ".").strip())
        assert rate >= 0
    except (ValueError, AssertionError):
        await edit_host(message, state, "📊 Введіть число ≥ 0:")
        return
    await state.update_data(debt_rate=rate)
    await state.set_state(AddDebt.waiting_date)
    await edit_host(
        message, state,
        f"📅 Дата наступного платежу <b>{DATE_HINT}</b>\n<i>або пропустіть:</i>",
        reply_markup=skip_keyboard("debt:skip_date", "cancel:debt"),
    )


@router.callback_query(F.data == "debt:skip_date")
async def debt_skip_date(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await _save_debt(callback, state, db_user, next_date=None)


@router.message(AddDebt.waiting_date)
async def debt_get_date(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        next_date = parse_date((message.text or "").strip())
    except ValueError:
        await edit_host(message, state, f"📅 Невірний формат. Введіть дату <b>{DATE_HINT}</b> або натисніть «Пропустити»:", reply_markup=skip_keyboard("debt:skip_date", "cancel:debt"))
        return
    await _save_debt(message, state, db_user, next_date=next_date)


async def _save_debt(target, state: FSMContext, db_user: User, next_date) -> None:
    data = await state.get_data()
    host_mid = None if isinstance(target, CallbackQuery) else data.get(HOST_MID_KEY)
    async with AsyncSessionLocal() as db:
        debt = Debt(
            user_id=db_user.id,
            name=data["debt_name"],
            total_amount=data["debt_total"],
            remaining_amount=data["debt_remaining"],
            monthly_payment=data["debt_monthly"],
            interest_rate=data["debt_rate"],
            next_payment_date=next_date,
            currency="UAH",
        )
        db.add(debt)
        await db.commit()
    await state.clear()
    if isinstance(target, CallbackQuery):
        await target.answer(f"✅ Борг «{data['debt_name']}» додано!", show_alert=True)
    await _show_debts(target, db_user, host_mid=host_mid)


@router.callback_query(F.data == "cancel:debt")
async def cancel_debt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await _show_debts(callback, db_user)


# ── Перегляд ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("debt:view:"))
async def view_debt(callback: CallbackQuery, db_user: User) -> None:
    debt_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == db_user.id))
        )
        d = result.scalar_one_or_none()

    if not d:
        await callback.answer("Борг не знайдено")
        return

    paid = d.total_amount - d.remaining_amount
    pct = round(paid / d.total_amount * 100, 1) if d.total_amount else 0
    date_str = f"\n📅 Наступний платіж: {fmt_date(d.next_payment_date)}" if d.next_payment_date else ""
    await callback.message.edit_text(
        f"💳 <b>{d.name}</b>\n\n"
        f"💰 Залишок: <b>{d.remaining_amount:.2f} {d.currency}</b>\n"
        f"📊 Погашено: {pct}% ({paid:.0f} / {d.total_amount:.0f})\n"
        f"💸 Щомісяч. платіж: {d.monthly_payment:.2f} {d.currency}\n"
        f"📈 Ставка: {d.interest_rate}% річних"
        f"{date_str}",
        reply_markup=debt_view_keyboard(debt_id),
    )
    await callback.answer()


# ── Видалення ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("debt:del_confirm:"))
async def debt_del_confirm(callback: CallbackQuery, db_user: User) -> None:
    debt_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == db_user.id))
        )
        d = result.scalar_one_or_none()
    name = d.name if d else f"#{debt_id}"
    await callback.message.edit_text(
        f"⚠️ Видалити борг «<b>{name}</b>»?\n\nЦе незворотньо.",
        reply_markup=confirm_delete_keyboard(
            confirm_cb=f"debt:delete:{debt_id}",
            cancel_cb=f"debt:view:{debt_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("debt:delete:"))
async def debt_delete(callback: CallbackQuery, db_user: User) -> None:
    debt_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == db_user.id))
        )
        debt = result.scalar_one_or_none()
        if debt:
            await db.delete(debt)
            await db.commit()
    await callback.answer("✅ Борг видалено")
    await _show_debts(callback, db_user)
