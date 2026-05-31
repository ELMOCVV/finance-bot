from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Account
from bot.keyboards.inline import (
    accounts_list_keyboard, currency_keyboard,
    account_view_keyboard, edit_account_keyboard,
    confirm_edit_keyboard, confirm_delete_keyboard, back_keyboard,
    currency_flag,
)
from bot.states import CreateAccount, EditAccount

router = Router()


async def _get_account(db_user: User, acc_id: int) -> Account | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Account).where(and_(Account.id == acc_id, Account.user_id == db_user.id))
        )
        return result.scalar_one_or_none()


async def _render_account_view(callback: CallbackQuery, db_user: User, acc_id: int) -> None:
    """Відображає деталі рахунку — спільна функція для view і після збереження."""
    acc = await _get_account(db_user, acc_id)
    if not acc:
        await callback.answer("Рахунок не знайдено")
        return
    flag = currency_flag(acc.currency)
    star = " ⭐ (за замовч.)" if acc.is_default else ""
    kw = ", ".join(acc.keywords) if acc.keywords else "—"
    await callback.message.edit_text(
        f"{flag} <b>{acc.name}</b>{star}\n\n"
        f"💵 Баланс: <b>{acc.balance:.2f} {acc.currency}</b>\n"
        f"🔑 Ключові слова: {kw}",
        reply_markup=account_view_keyboard(acc_id),
    )
    await callback.answer()


async def _show_accounts(target, db_user: User) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = result.scalars().all()

    text = "🏦 <b>Ваші рахунки:</b>" if accounts else "🏦 <b>Рахунків поки немає.</b>\nДодайте перший:"
    kb = accounts_list_keyboard(accounts)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


# ── Список ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:accounts")
async def show_accounts(callback: CallbackQuery, db_user: User) -> None:
    await _show_accounts(callback, db_user)


# ── Створення: крок 1 — назва ────────────────────────────────────────────────

@router.callback_query(F.data == "acc:add")
async def start_add_account(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateAccount.waiting_name)
    await callback.message.edit_text(
        "🏦 <b>Новий рахунок</b>\n\nВведіть назву рахунку:\n"
        "<i>Наприклад: Картка ПриватБанк, Готівка, USDT-гаманець</i>",
        reply_markup=back_keyboard("menu:accounts"),
    )
    await callback.answer()


@router.message(CreateAccount.waiting_name)
async def account_get_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("Введіть коректну назву (до 128 символів):")
        return
    await state.update_data(acc_name=name)
    await state.set_state(CreateAccount.waiting_currency)
    await message.answer("💱 Виберіть валюту рахунку:", reply_markup=currency_keyboard())


# ── Створення: крок 2 — валюта ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("currency:"), CreateAccount.waiting_currency)
async def account_get_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.split(":")[1]
    await state.update_data(acc_currency=currency)
    await state.set_state(CreateAccount.waiting_balance)
    await callback.message.edit_text(
        f"💵 Введіть поточний баланс рахунку ({currency}):\n"
        "<i>Введіть 0 якщо рахунок порожній</i>",
        reply_markup=back_keyboard("menu:accounts"),
    )
    await callback.answer()


# ── Створення: крок 3 — баланс ───────────────────────────────────────────────

@router.message(CreateAccount.waiting_balance)
async def account_get_balance(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        balance = float((message.text or "").replace(",", ".").strip())
        assert balance >= 0
    except (ValueError, AssertionError):
        await message.answer("Введіть коректне число ≥ 0:")
        return

    data = await state.get_data()
    acc_name = data["acc_name"]
    currency = data["acc_currency"]

    async with AsyncSessionLocal() as db:
        count_res = await db.execute(select(Account).where(Account.user_id == db_user.id))
        is_default = len(count_res.scalars().all()) == 0
        new_acc = Account(
            user_id=db_user.id,
            name=acc_name,
            currency=currency,
            balance=balance,
            is_default=is_default,
            keywords=[acc_name.lower()],
        )
        db.add(new_acc)
        await db.commit()
        await db.refresh(new_acc)

    await state.clear()
    await message.answer(
        f"✅ Рахунок «<b>{acc_name}</b>» створено!\n"
        f"💵 Баланс: {balance:.2f} {currency}",
        reply_markup=back_keyboard("menu:accounts"),
    )


@router.callback_query(F.data == "cancel:account")
async def cancel_account(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.clear()
    await _show_accounts(callback, db_user)


# ── Перегляд ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc:view:"))
async def view_account(callback: CallbackQuery, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    await _render_account_view(callback, db_user, acc_id)


# ── Редагування: меню ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc:edit:"))
async def show_edit_menu(callback: CallbackQuery, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    acc = await _get_account(db_user, acc_id)
    if not acc:
        await callback.answer("Рахунок не знайдено")
        return
    flag = currency_flag(acc.currency)
    await callback.message.edit_text(
        f"✏️ <b>Редагування: {flag} {acc.name}</b>\n\n"
        f"💵 Баланс: {acc.balance:.2f} {acc.currency}\n\n"
        "Що змінити?",
        reply_markup=edit_account_keyboard(acc_id, is_default=acc.is_default),
    )
    await callback.answer()


# ── Редагування: нова назва ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc:edit_name:"))
async def edit_name_prompt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    acc = await _get_account(db_user, acc_id)
    if not acc:
        await callback.answer("Рахунок не знайдено")
        return
    await state.set_state(EditAccount.waiting_name)
    await state.update_data(edit_acc_id=acc_id, edit_old_name=acc.name)
    await callback.message.edit_text(
        f"📝 Поточна назва: <b>«{acc.name}»</b>\n\nВведіть нову назву:",
        reply_markup=back_keyboard(f"acc:edit:{acc_id}"),
    )
    await callback.answer()


@router.message(EditAccount.waiting_name)
async def edit_name_input(message: Message, state: FSMContext) -> None:
    new_name = (message.text or "").strip()
    if not new_name or len(new_name) > 128:
        await message.answer("Введіть коректну назву (до 128 символів):")
        return
    data = await state.get_data()
    await state.update_data(edit_new_name=new_name)
    acc_id = data["edit_acc_id"]
    old_name = data["edit_old_name"]
    await message.answer(
        f"📝 Змінити назву\n"
        f"З: <b>«{old_name}»</b>\n"
        f"На: <b>«{new_name}»</b>",
        reply_markup=confirm_edit_keyboard(
            confirm_cb="acc:confirm_name",
            cancel_cb=f"acc:view:{acc_id}",
        ),
    )


@router.callback_query(F.data == "acc:confirm_name")
async def confirm_name(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    data = await state.get_data()
    acc_id = data.get("edit_acc_id")
    new_name = data.get("edit_new_name")
    if not acc_id or not new_name:
        await callback.answer("Сесія застаріла, спробуй ще раз")
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Account).where(and_(Account.id == acc_id, Account.user_id == db_user.id))
        )
        acc = result.scalar_one_or_none()
        if acc:
            acc.name = new_name
            acc.keywords = [new_name.lower()]
            await db.commit()
    await state.clear()
    await callback.answer("✅ Назву змінено!")
    await _render_account_view(callback, db_user, acc_id)


# ── Редагування: новий баланс ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc:edit_bal:"))
async def edit_balance_prompt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    acc = await _get_account(db_user, acc_id)
    if not acc:
        await callback.answer("Рахунок не знайдено")
        return
    await state.set_state(EditAccount.waiting_balance)
    await state.update_data(edit_acc_id=acc_id, edit_old_balance=acc.balance, edit_currency=acc.currency)
    await callback.message.edit_text(
        f"💵 Поточний баланс: <b>{acc.balance:.2f} {acc.currency}</b>\n\n"
        "Введіть новий баланс:",
        reply_markup=back_keyboard(f"acc:edit:{acc_id}"),
    )
    await callback.answer()


@router.message(EditAccount.waiting_balance)
async def edit_balance_input(message: Message, state: FSMContext) -> None:
    try:
        new_balance = float((message.text or "").replace(",", ".").strip())
        assert new_balance >= 0
    except (ValueError, AssertionError):
        await message.answer("Введіть коректне число ≥ 0:")
        return
    data = await state.get_data()
    await state.update_data(edit_new_balance=new_balance)
    acc_id = data["edit_acc_id"]
    old_balance = data["edit_old_balance"]
    currency = data["edit_currency"]
    await message.answer(
        f"💵 Змінити баланс\n"
        f"З: <b>{old_balance:.2f} {currency}</b>\n"
        f"На: <b>{new_balance:.2f} {currency}</b>",
        reply_markup=confirm_edit_keyboard(
            confirm_cb="acc:confirm_bal",
            cancel_cb=f"acc:view:{acc_id}",
        ),
    )


@router.callback_query(F.data == "acc:confirm_bal")
async def confirm_balance(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    data = await state.get_data()
    acc_id = data.get("edit_acc_id")
    new_balance = data.get("edit_new_balance")
    if acc_id is None or new_balance is None:
        await callback.answer("Сесія застаріла, спробуй ще раз")
        return
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Account).where(and_(Account.id == acc_id, Account.user_id == db_user.id))
        )
        acc = result.scalar_one_or_none()
        if acc:
            acc.balance = new_balance
            await db.commit()
    await state.clear()
    await callback.answer("✅ Баланс змінено!")
    await _render_account_view(callback, db_user, acc_id)


# ── Зробити основним ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc:set_default:"))
async def set_default_account(callback: CallbackQuery, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = result.scalars().all()
        target_name = None
        for acc in accounts:
            acc.is_default = (acc.id == acc_id)
            if acc.id == acc_id:
                target_name = acc.name
        await db.commit()
    await callback.answer(f"✅ Рахунок «{target_name}» тепер основний!", show_alert=True)
    await _render_account_view(callback, db_user, acc_id)


# ── Видалення ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("acc:del_confirm:"))
async def acc_del_confirm(callback: CallbackQuery, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    acc = await _get_account(db_user, acc_id)
    name = acc.name if acc else f"#{acc_id}"
    await callback.message.edit_text(
        f"⚠️ Видалити рахунок «<b>{name}</b>»?\n\n"
        "Всі транзакції по цьому рахунку залишаться в базі даних.",
        reply_markup=confirm_delete_keyboard(
            confirm_cb=f"acc:delete:{acc_id}",
            cancel_cb=f"acc:view:{acc_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acc:delete:"))
async def acc_delete(callback: CallbackQuery, db_user: User) -> None:
    acc_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Account).where(and_(Account.id == acc_id, Account.user_id == db_user.id))
        )
        acc = result.scalar_one_or_none()
        if acc:
            await db.delete(acc)
            await db.commit()
    await callback.answer("✅ Рахунок видалено")
    await _show_accounts(callback, db_user)
