from datetime import datetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import Account, Transfer, User
from app.services.exchange_rate_service import exchange_rate_service
from bot.keyboards.inline import (
    back_keyboard, currency_flag,
    transfer_account_keyboard, transfer_confirm_keyboard,
)
from bot.states import CreateTransfer

router = Router()


def _fmt(amount: float) -> str:
    if amount == int(amount):
        return f"{amount:,.0f}"
    return f"{amount:,.2f}"


async def _get_user_accounts(user_id: int) -> list[Account]:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Account).where(Account.user_id == user_id))
        return list(res.scalars().all())


# ── Крок 1: "З якого рахунку?" ───────────────────────────────────────────────

@router.callback_query(F.data == "menu:transfer")
async def start_transfer(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    accounts = await _get_user_accounts(db_user.id)
    if len(accounts) < 2:
        await callback.message.edit_text(
            "💸 <b>Переказ між рахунками</b>\n\n"
            "Для переказу потрібно щонайменше 2 рахунки.\n"
            "Спочатку додайте ще один рахунок:",
            reply_markup=back_keyboard("menu:accounts"),
        )
        await callback.answer()
        return

    await state.set_state(CreateTransfer.selecting_from)
    await callback.message.edit_text(
        "💸 <b>Переказ між рахунками</b>\n\nЗ якого рахунку перекажемо?",
        reply_markup=transfer_account_keyboard(accounts, "from"),
    )
    await callback.answer()


# ── Крок 2: "На який рахунок?" ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("transfer:from:"), CreateTransfer.selecting_from)
async def transfer_pick_from(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    from_id = int(callback.data.split(":")[2])
    accounts = await _get_user_accounts(db_user.id)
    from_acc = next((a for a in accounts if a.id == from_id), None)
    if not from_acc:
        await callback.answer("Рахунок не знайдено")
        return

    others = [a for a in accounts if a.id != from_id]
    await state.update_data(from_account_id=from_id)
    await state.set_state(CreateTransfer.selecting_to)
    flag = currency_flag(from_acc.currency)
    await callback.message.edit_text(
        "💸 <b>Переказ між рахунками</b>\n\n"
        f"З: {flag} {from_acc.name} — {_fmt(from_acc.balance)} {from_acc.currency}\n\n"
        "На який рахунок перекажемо?",
        reply_markup=transfer_account_keyboard(others, "to"),
    )
    await callback.answer()


# ── Крок 3: "Введіть суму" ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("transfer:to:"), CreateTransfer.selecting_to)
async def transfer_pick_to(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    to_id = int(callback.data.split(":")[2])
    data = await state.get_data()
    accounts = await _get_user_accounts(db_user.id)
    from_acc = next((a for a in accounts if a.id == data.get("from_account_id")), None)
    to_acc = next((a for a in accounts if a.id == to_id), None)
    if not from_acc or not to_acc:
        await callback.answer("Рахунок не знайдено")
        return

    await state.update_data(to_account_id=to_id)
    await state.set_state(CreateTransfer.waiting_amount)
    from_flag = currency_flag(from_acc.currency)
    to_flag = currency_flag(to_acc.currency)
    await callback.message.edit_text(
        "💸 <b>Переказ між рахунками</b>\n\n"
        f"З: {from_flag} {from_acc.name} — {_fmt(from_acc.balance)} {from_acc.currency}\n"
        f"На: {to_flag} {to_acc.name} — {_fmt(to_acc.balance)} {to_acc.currency}\n\n"
        f"Введіть суму переказу (у {from_acc.currency}):",
        reply_markup=back_keyboard("menu:transfer"),
    )
    await callback.answer()


# ── Крок 4: підтвердження ────────────────────────────────────────────────────

@router.message(CreateTransfer.waiting_amount)
async def transfer_get_amount(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        amount = float((message.text or "").replace(",", ".").replace(" ", "").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await message.answer("Введіть коректне число більше 0:")
        return

    data = await state.get_data()
    accounts = await _get_user_accounts(db_user.id)
    from_acc = next((a for a in accounts if a.id == data.get("from_account_id")), None)
    to_acc = next((a for a in accounts if a.id == data.get("to_account_id")), None)
    if not from_acc or not to_acc:
        await state.clear()
        await message.answer("Сесія застаріла, спробуйте ще раз.", reply_markup=back_keyboard())
        return

    converted = amount
    rate_line = None
    if from_acc.currency.upper() != to_acc.currency.upper():
        rate = await exchange_rate_service.get_rate(from_acc.currency, to_acc.currency)
        if rate is not None:
            converted = round(amount * rate, 2)
            rate_line = (
                f"💱 Курс: 1 {from_acc.currency} ≈ {rate:.4f} {to_acc.currency}\n"
                f"Зарахується: <b>{_fmt(converted)} {to_acc.currency}</b>"
            )
        else:
            rate_line = "⚠️ Курс конвертації недоступний — суму буде зараховано без конвертації"

    await state.update_data(transfer_amount=amount, converted_amount=converted)
    await state.set_state(CreateTransfer.confirming)

    from_flag = currency_flag(from_acc.currency)
    to_flag = currency_flag(to_acc.currency)
    lines = [
        "💸 <b>Переказ</b>\n",
        f"З: {from_flag} {from_acc.name} — {_fmt(from_acc.balance)} {from_acc.currency}",
        f"На: {to_flag} {to_acc.name} — {_fmt(to_acc.balance)} {to_acc.currency}",
        "",
        f"Сума: <b>{_fmt(amount)} {from_acc.currency}</b>",
    ]
    if rate_line:
        lines.append(rate_line)
    lines.append("\n✅ Підтвердити | ❌ Скасувати")

    await message.answer("\n".join(lines), reply_markup=transfer_confirm_keyboard())


# ── Підтвердження і виконання переказу ───────────────────────────────────────

@router.callback_query(F.data == "transfer:confirm", CreateTransfer.confirming)
async def transfer_confirm(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    data = await state.get_data()
    from_id = data.get("from_account_id")
    to_id = data.get("to_account_id")
    amount = data.get("transfer_amount")
    converted = data.get("converted_amount", amount)

    if not from_id or not to_id or amount is None:
        await state.clear()
        await callback.answer("Сесія застаріла, спробуйте ще раз")
        return

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Account).where(and_(Account.id.in_([from_id, to_id]), Account.user_id == db_user.id))
        )
        accs = {a.id: a for a in res.scalars().all()}
        from_acc = accs.get(from_id)
        to_acc = accs.get(to_id)
        if not from_acc or not to_acc:
            await state.clear()
            await callback.answer("Рахунок не знайдено")
            return

        from_acc.balance -= amount
        to_acc.balance += converted
        amount_uah = await exchange_rate_service.to_uah(amount, from_acc.currency)

        db.add(Transfer(
            user_id=db_user.id,
            from_account_id=from_id,
            to_account_id=to_id,
            amount=amount,
            currency=from_acc.currency,
            amount_uah=amount_uah,
            date=datetime.utcnow(),
        ))
        await db.commit()
        await db.refresh(from_acc)
        await db.refresh(to_acc)

        from_flag = currency_flag(from_acc.currency)
        to_flag = currency_flag(to_acc.currency)
        result_text = (
            "✅ <b>Переказ виконано!</b>\n\n"
            f"{from_flag} {from_acc.name}: <b>{_fmt(from_acc.balance)} {from_acc.currency}</b>\n"
            f"{to_flag} {to_acc.name}: <b>{_fmt(to_acc.balance)} {to_acc.currency}</b>"
        )

    await state.clear()
    await callback.message.edit_text(result_text, reply_markup=back_keyboard())
    await callback.answer("✅ Переказ виконано")


# ── Перегляд переказу зі списку транзакцій ───────────────────────────────────

@router.callback_query(F.data.startswith("transfer:view:"))
async def view_transfer(callback: CallbackQuery, db_user: User) -> None:
    transfer_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Transfer).where(and_(Transfer.id == transfer_id, Transfer.user_id == db_user.id))
        )
        tr = res.scalar_one_or_none()
        from_acc = await db.get(Account, tr.from_account_id) if tr else None
        to_acc = await db.get(Account, tr.to_account_id) if tr else None

    if not tr:
        await callback.answer("Переказ не знайдено")
        return

    from_flag = currency_flag(from_acc.currency) if from_acc else "💱"
    to_flag = currency_flag(to_acc.currency) if to_acc else "💱"
    date_str = tr.date.strftime("%d.%m.%Y %H:%M")
    await callback.message.edit_text(
        "🔄 <b>ПЕРЕКАЗ</b>\n\n"
        f"З: {from_flag} {from_acc.name if from_acc else '—'}\n"
        f"На: {to_flag} {to_acc.name if to_acc else '—'}\n"
        f"💵 Сума: <b>{_fmt(tr.amount)} {tr.currency}</b> (~{tr.amount_uah:,.2f} ₴)\n"
        f"📅 Дата: {date_str}",
        reply_markup=back_keyboard("menu:transactions"),
    )
    await callback.answer()
