import logging
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Account
from app.models.subscription import Subscription
from bot.keyboards.inline import (
    subscriptions_keyboard, subscription_view_keyboard,
    edit_subscription_keyboard, sub_period_keyboard,
    sub_currency_keyboard, sub_month_keyboard, sub_account_keyboard,
    confirm_delete_keyboard, back_keyboard, MONTHS_UA_GEN,
)
from bot.states import CreateSubscription, EditSubscription
from bot.utils.fsm_edit import edit_host, HOST_MID_KEY

logger = logging.getLogger(__name__)
router = Router()


# ── Утиліти відображення ──────────────────────────────────────────────────────

def _sub_period_label(sub: Subscription) -> str:
    if sub.period == "monthly":
        return f"Щомісячна, {sub.day_of_month}-го числа"
    month_name = MONTHS_UA_GEN[sub.month_of_year - 1] if sub.month_of_year else "?"
    return f"Щорічна, {sub.day_of_month} {month_name}"


async def _show_subscriptions(target, db_user: User, host_mid: int | None = None) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription)
            .where(Subscription.user_id == db_user.id)
            .order_by(Subscription.is_active.desc(), Subscription.day_of_month)
        )
        subs = result.scalars().all()

    text = "🔔 <b>Ваші підписки:</b>" if subs else "🔔 <b>Підписок поки немає.</b>\nДодайте першу:"
    kb = subscriptions_keyboard(subs)

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


async def _render_sub_view(callback: CallbackQuery, db_user: User, sub_id: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()

    if not sub:
        await callback.answer("Підписку не знайдено")
        return

    acc_text = "—"
    if sub.account_id:
        async with AsyncSessionLocal() as db:
            acc = await db.get(Account, sub.account_id)
            if acc:
                acc_text = f"{acc.name} ({acc.balance:.2f} {acc.currency})"

    status = "✅ Активна" if sub.is_active else "⏸ Призупинена"
    await callback.message.edit_text(
        f"🔔 <b>{sub.name}</b>\n\n"
        f"💸 Сума: <b>{sub.amount:.2f} {sub.currency}</b>\n"
        f"📅 Тип: {_sub_period_label(sub)}\n"
        f"🕐 Нагадування: о {sub.remind_hour:02d}:00\n"
        f"🏦 Рахунок: {acc_text}\n"
        f"{'✅' if sub.is_active else '⏸'} Статус: {status}",
        reply_markup=subscription_view_keyboard(sub_id, sub.is_active),
    )
    await callback.answer()


# ── Список ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:subscriptions")
async def show_subscriptions(callback: CallbackQuery, db_user: User) -> None:
    await _show_subscriptions(callback, db_user)


# ── Перегляд / Перемикання / Видалення ───────────────────────────────────────

@router.callback_query(F.data.startswith("sub:view:"))
async def view_subscription(callback: CallbackQuery, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    await _render_sub_view(callback, db_user, sub_id)


@router.callback_query(F.data.startswith("sub:toggle:"))
async def toggle_subscription(callback: CallbackQuery, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
        if not sub:
            await callback.answer("Підписку не знайдено")
            return
        sub.is_active = not sub.is_active
        await db.commit()
        status = "активовано" if sub.is_active else "призупинено"
        await callback.answer(f"{'▶️' if sub.is_active else '⏸'} Підписку {status}")
    await _render_sub_view(callback, db_user, sub_id)


@router.callback_query(F.data.startswith("sub:del_confirm:"))
async def sub_del_confirm(callback: CallbackQuery, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
    name = sub.name if sub else f"#{sub_id}"
    await callback.message.edit_text(
        f"⚠️ Видалити підписку «<b>{name}</b>»?\n\nЦе незворотньо.",
        reply_markup=confirm_delete_keyboard(
            confirm_cb=f"sub:delete:{sub_id}",
            cancel_cb=f"sub:view:{sub_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:delete:"))
async def sub_delete(callback: CallbackQuery, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
        if sub:
            await db.delete(sub)
            await db.commit()
    await callback.answer("✅ Підписку видалено")
    await _show_subscriptions(callback, db_user)


# ── Редагування ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sub:edit:"))
async def show_edit_sub(callback: CallbackQuery, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
    if not sub:
        await callback.answer("Підписку не знайдено")
        return
    await callback.message.edit_text(
        f"✏️ <b>Редагування: {sub.name}</b>\n\n"
        f"💸 {sub.amount:.2f} {sub.currency} | 🕐 {sub.remind_hour:02d}:00\n\n"
        "Що змінити?",
        reply_markup=edit_subscription_keyboard(sub_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("sub:edit_name:"))
async def edit_sub_name_prompt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
    if not sub:
        await callback.answer("Підписку не знайдено")
        return
    await state.set_state(EditSubscription.waiting_name)
    await state.update_data(edit_sub_id=sub_id, **{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text(
        f"📝 Поточна назва: <b>«{sub.name}»</b>\n\nВведіть нову назву:",
        reply_markup=back_keyboard(f"sub:edit:{sub_id}"),
    )
    await callback.answer()


@router.message(EditSubscription.waiting_name)
async def edit_sub_name_input(message: Message, state: FSMContext, db_user: User) -> None:
    new_name = (message.text or "").strip()
    if not new_name or len(new_name) > 256:
        await edit_host(message, state, "📝 Введіть коректну назву (до 256 символів):")
        return
    data = await state.get_data()
    sub_id = data["edit_sub_id"]
    host_mid = data.get(HOST_MID_KEY)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.name = new_name
            await db.commit()
    await state.clear()
    text = f"✅ Назву змінено на «{new_name}»"
    if host_mid:
        try:
            await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=host_mid, reply_markup=back_keyboard(f"sub:view:{sub_id}"), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=back_keyboard(f"sub:view:{sub_id}"))


@router.callback_query(F.data.startswith("sub:edit_amount:"))
async def edit_sub_amount_prompt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
    if not sub:
        await callback.answer("Підписку не знайдено")
        return
    await state.set_state(EditSubscription.waiting_amount)
    await state.update_data(edit_sub_id=sub_id, edit_sub_currency=sub.currency, **{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text(
        f"💵 Поточна сума: <b>{sub.amount:.2f} {sub.currency}</b>\n\nВведіть нову суму:",
        reply_markup=back_keyboard(f"sub:edit:{sub_id}"),
    )
    await callback.answer()


@router.message(EditSubscription.waiting_amount)
async def edit_sub_amount_input(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await edit_host(message, state, "💵 Введіть коректне число більше 0:")
        return
    data = await state.get_data()
    sub_id = data["edit_sub_id"]
    currency = data["edit_sub_currency"]
    host_mid = data.get(HOST_MID_KEY)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.amount = amount
            await db.commit()
    await state.clear()
    text = f"✅ Суму змінено: {amount:.2f} {currency}"
    if host_mid:
        try:
            await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=host_mid, reply_markup=back_keyboard(f"sub:view:{sub_id}"), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=back_keyboard(f"sub:view:{sub_id}"))


@router.callback_query(F.data.startswith("sub:edit_hour:"))
async def edit_sub_hour_prompt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    sub_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
    if not sub:
        await callback.answer("Підписку не знайдено")
        return
    await state.set_state(EditSubscription.waiting_hour)
    await state.update_data(edit_sub_id=sub_id, **{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text(
        f"🕐 Поточний час нагадування: <b>{sub.remind_hour:02d}:00</b>\n\n"
        "Введіть годину (0-23):",
        reply_markup=back_keyboard(f"sub:edit:{sub_id}"),
    )
    await callback.answer()


@router.message(EditSubscription.waiting_hour)
async def edit_sub_hour_input(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        hour = int((message.text or "").strip())
        assert 0 <= hour <= 23
    except (ValueError, AssertionError):
        await edit_host(message, state, "🕐 Введіть число від 0 до 23:")
        return
    data = await state.get_data()
    sub_id = data["edit_sub_id"]
    host_mid = data.get(HOST_MID_KEY)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(Subscription.id == sub_id, Subscription.user_id == db_user.id)
            )
        )
        sub = result.scalar_one_or_none()
        if sub:
            sub.remind_hour = hour
            await db.commit()
    await state.clear()
    text = f"✅ Нагадування о {hour:02d}:00"
    if host_mid:
        try:
            await message.bot.edit_message_text(text, chat_id=message.chat.id, message_id=host_mid, reply_markup=back_keyboard(f"sub:view:{sub_id}"), parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=back_keyboard(f"sub:view:{sub_id}"))


# ── Створення — крок 1: назва ─────────────────────────────────────────────────

@router.callback_query(F.data == "sub:add")
async def start_add_sub(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CreateSubscription.waiting_name)
    await state.update_data(**{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text(
        "🔔 <b>Нова підписка</b>\n\nВведіть назву підписки:\n"
        "<i>Наприклад: Netflix, Spotify, ChatGPT Plus</i>",
        reply_markup=back_keyboard("menu:subscriptions"),
    )
    await callback.answer()


@router.message(CreateSubscription.waiting_name)
async def sub_get_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 256:
        await edit_host(message, state, "🔔 Введіть коректну назву (до 256 символів):", reply_markup=back_keyboard("menu:subscriptions"))
        return
    await state.update_data(sub_name=name)
    await state.set_state(CreateSubscription.waiting_amount)
    await edit_host(message, state, f"🔔 <b>{name}</b>\n\nВведіть суму списання:")


# ── Крок 2: сума ──────────────────────────────────────────────────────────────

@router.message(CreateSubscription.waiting_amount)
async def sub_get_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await edit_host(message, state, "💸 Введіть коректне число більше 0:")
        return
    await state.update_data(sub_amount=amount)
    await state.set_state(CreateSubscription.waiting_currency)
    await edit_host(message, state, "💱 Виберіть валюту:", reply_markup=sub_currency_keyboard())


# ── Крок 3: валюта ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("subcur:"), CreateSubscription.waiting_currency)
async def sub_get_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.split(":")[1]
    await state.update_data(sub_currency=currency)
    await state.set_state(CreateSubscription.waiting_period)
    await callback.message.edit_text(
        "📅 Тип підписки:",
        reply_markup=sub_period_keyboard(),
    )
    await callback.answer()


# ── Крок 4: тип (monthly/yearly) ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("sub:period:"), CreateSubscription.waiting_period)
async def sub_get_period(callback: CallbackQuery, state: FSMContext) -> None:
    period = callback.data.split(":")[2]
    await state.update_data(sub_period=period)
    await state.set_state(CreateSubscription.waiting_day)
    await callback.message.edit_text(
        "📅 Введіть день місяця списання (1-31):",
        reply_markup=back_keyboard("menu:subscriptions"),
    )
    await callback.answer()


# ── Крок 5: день ──────────────────────────────────────────────────────────────

@router.message(CreateSubscription.waiting_day)
async def sub_get_day(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        day = int((message.text or "").strip())
        assert 1 <= day <= 31
    except (ValueError, AssertionError):
        await edit_host(message, state, "📅 Введіть число від 1 до 31:")
        return
    data = await state.update_data(sub_day=day)
    if data.get("sub_period") == "yearly":
        await state.set_state(CreateSubscription.waiting_month)
        await edit_host(message, state, "📆 Виберіть місяць:", reply_markup=sub_month_keyboard())
    else:
        await state.set_state(CreateSubscription.waiting_account)
        await _show_account_selection(message, db_user)


# ── Крок 6 (yearly): місяць ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("sub:month:"), CreateSubscription.waiting_month)
async def sub_get_month(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    month = int(callback.data.split(":")[2])
    await state.update_data(sub_month=month)
    await state.set_state(CreateSubscription.waiting_account)
    await _show_account_selection(callback, db_user)
    await callback.answer()


# ── Крок 7: рахунок ───────────────────────────────────────────────────────────

async def _show_account_selection(target, db_user: User) -> None:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = res.scalars().all()
    text = "🏦 Прив'язати до рахунку (або пропустити):"
    kb = sub_account_keyboard(accounts)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "sub:no_acc", CreateSubscription.waiting_account)
async def sub_no_account(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sub_account_id=None)
    await state.set_state(CreateSubscription.waiting_hour)
    await _ask_remind_hour(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("sub:acc:"), CreateSubscription.waiting_account)
async def sub_select_account(callback: CallbackQuery, state: FSMContext) -> None:
    acc_id = int(callback.data.split(":")[2])
    await state.update_data(sub_account_id=acc_id)
    await state.set_state(CreateSubscription.waiting_hour)
    await _ask_remind_hour(callback)
    await callback.answer()


async def _ask_remind_hour(target) -> None:
    text = "🕐 О котрій годині надсилати нагадування? (введіть 0-23)\n<i>Наприклад: 9 — о 09:00</i>"
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=back_keyboard("menu:subscriptions"))
    else:
        await target.answer(text, reply_markup=back_keyboard("menu:subscriptions"))


# ── Крок 8: година → зберегти ────────────────────────────────────────────────

@router.message(CreateSubscription.waiting_hour)
async def sub_get_hour(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        hour = int((message.text or "").strip())
        assert 0 <= hour <= 23
    except (ValueError, AssertionError):
        await edit_host(message, state, "🕐 Введіть число від 0 до 23:")
        return

    data = await state.get_data()
    host_mid = data.get(HOST_MID_KEY)
    async with AsyncSessionLocal() as db:
        sub = Subscription(
            user_id=db_user.id,
            name=data["sub_name"],
            amount=data["sub_amount"],
            currency=data["sub_currency"],
            period=data["sub_period"],
            day_of_month=data["sub_day"],
            month_of_year=data.get("sub_month"),
            account_id=data.get("sub_account_id"),
            remind_hour=hour,
            is_active=True,
        )
        db.add(sub)
        await db.commit()

    await state.clear()
    await _show_subscriptions(message, db_user, host_mid=host_mid)
