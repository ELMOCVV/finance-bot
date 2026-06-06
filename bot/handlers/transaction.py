import logging
from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Account, Category
from app.services.claude_service import claude_service
from bot.keyboards.inline import (
    accounts_list_keyboard,
    confirm_transaction_keyboard,
    confirm_multi_transaction_keyboard,
    multi_tx_select_keyboard,
    new_category_keyboard,
    edit_transaction_keyboard,
    tx_account_select_keyboard,
    transaction_view_keyboard,
    confirm_delete_keyboard,
    categories_keyboard,
    back_keyboard,
    main_menu_keyboard,
)
from bot.services.category_matcher import match_category
from bot.states import AddTransaction, EditTransaction
from bot.utils.tx_helpers import build_confirmation_text, build_multi_confirmation_text, save_transaction

logger = logging.getLogger(__name__)
router = Router()

# Захист від циклу: зберігаємо (chat_id, message_id) вже оброблених повідомлень
_processed_ids: set[tuple[int, int]] = set()
_MAX_PROCESSED = 500


def _check_and_mark(chat_id: int, msg_id: int) -> bool:
    """Повертає True якщо повідомлення вже оброблялось (дублікат)."""
    key = (chat_id, msg_id)
    if key in _processed_ids:
        return True
    _processed_ids.add(key)
    if len(_processed_ids) > _MAX_PROCESSED:
        _processed_ids.clear()
    return False


# ────────────────────────────────────────────────────────────────
# Спільна логіка: парсинг + підбір категорії + показ підтвердження
# ────────────────────────────────────────────────────────────────

async def _parse_and_show(
    message: Message,
    db_user: User,
    text: str,
    state: FSMContext,
    force_type: str | None = None,
) -> None:
    """Парсить текст транзакції та показує підтвердження (одиночне або кілька)."""
    async with AsyncSessionLocal() as db:
        acc_res = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = acc_res.scalars().all()

    if not accounts:
        await message.answer(
            "⚠️ У вас ще немає рахунків.\nСпочатку створіть рахунок:",
            reply_markup=accounts_list_keyboard([]),
        )
        await state.clear()
        return

    status_msg = await message.answer("⏳ Аналізую транзакцію...")
    parsed = await claude_service.parse_transaction(text)

    # Кілька транзакцій → multi-flow
    if isinstance(parsed, list):
        await _parse_and_show_multi(message, db_user, parsed, accounts, state, status_msg)
        return

    if "error" in parsed:
        await status_msg.edit_text(
            f"❌ Не вдалось розпарсити.\n{parsed['error']}\n\n"
            "<i>Спробуй: «Кава 50 грн»</i>",
        )
        await state.clear()
        return

    tx_type = force_type or parsed.get("type", "expense")
    account = _find_account(accounts, parsed.get("account_hint"))

    async with AsyncSessionLocal() as db:
        cat_res = await db.execute(
            select(Category).where(
                and_(Category.user_id == db_user.id, Category.type == tx_type)
            )
        )
        user_cats = cat_res.scalars().all()

    cats_for_matcher = [{"id": c.id, "name": c.name} for c in user_cats]
    cat_match = await match_category(
        description=parsed.get("description", ""),
        hint=parsed.get("category_hint", ""),
        tx_type=tx_type,
        user_categories=cats_for_matcher,
    )

    state_data = {
        "parsed": parsed,
        "tx_type": tx_type,
        "amount": parsed.get("amount"),
        "currency": parsed.get("currency", "UAH"),
        "description": parsed.get("description"),
        "account_id": account.id,
        "account_name": account.name,
        "source": "bot_text",
    }

    if "matched_id" in cat_match:
        state_data["category_id"] = cat_match["matched_id"]
        state_data["category_name"] = cat_match["name"]
        state_data["is_new_cat"] = False
        keyboard = confirm_transaction_keyboard()
    else:
        state_data["category_id"] = None
        state_data["category_name"] = "—"
        state_data["is_new_cat"] = True
        state_data["new_cat_name"] = cat_match.get("new_name", "Інше")
        keyboard = new_category_keyboard(state_data["new_cat_name"])

    await state.update_data(**state_data)
    await status_msg.edit_text(
        build_confirmation_text(state_data),
        reply_markup=keyboard,
    )


async def _parse_and_show_multi(
    message: Message,
    db_user: User,
    parsed_list: list,
    accounts: list,
    state: FSMContext,
    status_msg=None,
) -> None:
    """Обробляє кілька транзакцій одночасно."""
    valid_items = [p for p in parsed_list if isinstance(p, dict) and "error" not in p]
    if not valid_items:
        err = "❌ Не вдалось розпарсити транзакції."
        if status_msg:
            await status_msg.edit_text(err)
        else:
            await message.answer(err)
        await state.clear()
        return

    async with AsyncSessionLocal() as db:
        cat_res = await db.execute(select(Category).where(Category.user_id == db_user.id))
        all_cats = cat_res.scalars().all()

    multi_txs = []
    for parsed in valid_items:
        tx_type = parsed.get("type", "expense")
        account = _find_account(accounts, parsed.get("account_hint"))
        cats_for_type = [{"id": c.id, "name": c.name} for c in all_cats if c.type == tx_type]

        cat_match = await match_category(
            description=parsed.get("description", ""),
            hint=parsed.get("category_hint", ""),
            tx_type=tx_type,
            user_categories=cats_for_type,
        )

        tx_data: dict = {
            "parsed": parsed,
            "tx_type": tx_type,
            "amount": parsed.get("amount"),
            "currency": parsed.get("currency", "UAH"),
            "description": parsed.get("description"),
            "account_id": account.id,
            "account_name": account.name,
            "source": "bot_text",
            "is_new_cat": False,
        }

        if "matched_id" in cat_match:
            tx_data["category_id"] = cat_match["matched_id"]
            tx_data["category_name"] = cat_match["name"]
        else:
            tx_data["category_id"] = None
            tx_data["category_name"] = "Інше"

        multi_txs.append(tx_data)

    await state.clear()
    await state.update_data(multi_txs=multi_txs)
    text = build_multi_confirmation_text(multi_txs)
    kb = confirm_multi_transaction_keyboard()

    if status_msg:
        await status_msg.edit_text(text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


def _find_account(accounts: list, hint: str | None) -> Account:
    """Знаходить рахунок за підказкою або повертає дефолтний/перший."""
    if hint:
        h = hint.lower()
        for acc in accounts:
            kws = acc.keywords or []
            if any(h in kw.lower() for kw in kws) or h in acc.name.lower():
                return acc
    for acc in accounts:
        if acc.is_default:
            return acc
    return accounts[0]


# ────────────────────────────────────────────────────────────────
# Вхідні точки: вільний текст і стан "очікую текст"
# ────────────────────────────────────────────────────────────────

@router.message(AddTransaction.waiting_text)
async def handle_transaction_from_state(message: Message, db_user: User, state: FSMContext) -> None:
    """Обробляє текст після натискання «💸 Витрата»."""
    if _check_and_mark(message.chat.id, message.message_id):
        return
    await _parse_and_show(message, db_user, message.text.strip(), state)


@router.message(AddTransaction.waiting_income_text)
async def handle_income_from_state(message: Message, db_user: User, state: FSMContext) -> None:
    """Обробляє текст після натискання «💰 Дохід» — тип income примусовий."""
    if _check_and_mark(message.chat.id, message.message_id):
        return
    await _parse_and_show(message, db_user, message.text.strip(), state, force_type="income")


@router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, db_user: User, state: FSMContext) -> None:
    """Вільний текст: числа → транзакція, решта → AI-питання."""
    if _check_and_mark(message.chat.id, message.message_id):
        return
    text = message.text.strip()
    has_digit = any(c.isdigit() for c in text)
    if has_digit and len(text) <= 300:
        await _parse_and_show(message, db_user, text, state)
    else:
        await message.answer("🤔 Думаю...")
        answer = await claude_service.answer_finance_question(text)
        await message.answer(answer)


# ────────────────────────────────────────────────────────────────
# Multi-транзакції: підтвердження / редагування / скасування
# ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "multi:confirm")
async def confirm_multi_tx(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    data = await state.get_data()
    multi_txs = data.get("multi_txs", [])
    if not multi_txs:
        await callback.answer("Транзакції не знайдено. Спробуй ще раз.")
        return

    saved = []
    for tx_data in multi_txs:
        tx = await save_transaction(db_user.id, tx_data)
        saved.append(tx)

    await state.clear()
    lines = ["✅ <b>Збережено!</b>\n"]
    for tx in saved:
        lines.append(f"• {tx.amount:.2f} {tx.currency} — {tx.description or '—'}")
    await callback.message.edit_text("\n".join(lines), reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "multi:cancel")
async def cancel_multi_tx(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Транзакції скасовано.", reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "multi:edit")
async def edit_multi_tx_select(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    multi_txs = data.get("multi_txs", [])
    await callback.message.edit_text(
        "✏️ <b>Яку транзакцію редагуємо?</b>",
        reply_markup=multi_tx_select_keyboard(multi_txs),
    )
    await callback.answer()


@router.callback_query(F.data == "multi:back")
async def multi_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    multi_txs = data.get("multi_txs", [])
    await callback.message.edit_text(
        build_multi_confirmation_text(multi_txs),
        reply_markup=confirm_multi_transaction_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("multi:edit:"))
async def edit_multi_tx_item(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    multi_txs = data.get("multi_txs", [])
    if idx >= len(multi_txs):
        await callback.answer("Транзакцію не знайдено")
        return

    tx = multi_txs[idx]
    # Розгортаємо вибрану транзакцію в single-tx поля для редагування
    await state.update_data(
        parsed=tx.get("parsed", {}),
        tx_type=tx["tx_type"],
        amount=tx["amount"],
        currency=tx["currency"],
        description=tx["description"],
        account_id=tx["account_id"],
        account_name=tx["account_name"],
        category_id=tx.get("category_id"),
        category_name=tx.get("category_name", "Інше"),
        is_new_cat=tx.get("is_new_cat", False),
        new_cat_name=tx.get("new_cat_name", ""),
        source=tx.get("source", "bot_text"),
        multi_editing=True,
        multi_editing_index=idx,
    )

    is_other = not tx.get("category_id") and tx.get("category_name") in ("Інше", "—", None)
    await callback.message.edit_text(
        f"✏️ <b>Редагуємо #{idx + 1}:</b>\n\n" + build_confirmation_text(tx),
        reply_markup=edit_transaction_keyboard(show_new_cat=is_other),
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────
# Підтвердження / скасування (одиночна)
# ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "tx:confirm")
async def confirm_tx(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    data = await state.get_data()
    if not data or "parsed" not in data:
        await callback.answer("Транзакцію не знайдено. Спробуй ще раз.")
        return
    tx = await save_transaction(db_user.id, data)
    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Збережено!</b>\n\n"
        f"💵 {tx.amount:.2f} {tx.currency} ({tx.amount_uah:.2f} ₴)\n"
        f"📝 {tx.description or '—'}",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "tx:cancel")
async def cancel_tx(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("❌ Транзакцію скасовано.", reply_markup=back_keyboard())
    await callback.answer()


# ── Нова категорія ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("newcat:create:"))
async def newcat_create(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    data = await state.get_data()
    if not data or "parsed" not in data:
        await callback.answer("Сесія застаріла. Введи транзакцію ще раз.")
        return

    cat_name = callback.data[len("newcat:create:"):]
    tx_type = data.get("tx_type", "expense")

    async with AsyncSessionLocal() as db:
        cat = Category(user_id=db_user.id, name=cat_name, type=tx_type)
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

    await state.update_data(category_id=cat.id, category_name=cat_name, is_new_cat=False)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx]["category_id"] = cat.id
        multi_txs[idx]["category_name"] = cat_name
        multi_txs[idx]["is_new_cat"] = False
        await state.update_data(multi_txs=multi_txs, multi_editing=False)
        data = await state.get_data()
        await callback.message.edit_text(
            build_multi_confirmation_text(multi_txs),
            reply_markup=confirm_multi_transaction_keyboard(),
        )
        await callback.answer()
        return

    tx = await save_transaction(db_user.id, data)
    await state.clear()
    await callback.message.edit_text(
        f"✅ <b>Категорію «{cat_name}» створено і транзакцію збережено!</b>\n\n"
        f"💵 {tx.amount:.2f} {tx.currency}",
        reply_markup=back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "newcat:pick")
async def newcat_pick(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    data = await state.get_data()
    tx_type = data.get("tx_type", "expense")
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category).where(
                and_(Category.user_id == db_user.id, Category.type == tx_type)
            )
        )
        cats = res.scalars().all()

    await callback.message.edit_text(
        "🏷 Виберіть категорію:",
        reply_markup=categories_keyboard(cats, back_cb="txedit:back"),
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────
# Редагування
# ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "tx:edit")
async def start_edit(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "✏️ <b>Що редагуємо?</b>",
        reply_markup=edit_transaction_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "txedit:back")
async def edit_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx].update({
            "parsed": data.get("parsed", {}),
            "tx_type": data.get("tx_type", "expense"),
            "amount": data.get("amount"),
            "currency": data.get("currency", "UAH"),
            "description": data.get("description"),
            "account_id": data.get("account_id"),
            "account_name": data.get("account_name", "—"),
            "category_id": data.get("category_id"),
            "category_name": data.get("category_name", "Інше"),
            "is_new_cat": data.get("is_new_cat", False),
            "new_cat_name": data.get("new_cat_name", ""),
        })
        await state.update_data(multi_txs=multi_txs, multi_editing=False)
        await callback.message.edit_text(
            build_multi_confirmation_text(multi_txs),
            reply_markup=confirm_multi_transaction_keyboard(),
        )
        await callback.answer()
        return

    if not data or "parsed" not in data:
        await callback.message.edit_text("Сесія застаріла.", reply_markup=back_keyboard())
        await callback.answer()
        return
    kb = new_category_keyboard(data["new_cat_name"]) if data.get("is_new_cat") else confirm_transaction_keyboard()
    await callback.message.edit_text(build_confirmation_text(data), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "txedit:amount")
async def edit_amount_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditTransaction.editing_amount)
    await callback.message.edit_text(
        "💵 Введіть нову суму:",
        reply_markup=back_keyboard("txedit:back"),
    )
    await callback.answer()


@router.message(EditTransaction.editing_amount)
async def edit_amount_input(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").replace(",", ".").strip())
        assert amount > 0
    except (ValueError, AssertionError):
        await message.answer("Введіть коректне число більше 0:")
        return
    await state.update_data(amount=amount)
    await state.set_state(None)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx]["amount"] = amount
        await state.update_data(multi_txs=multi_txs)
        await message.answer(build_multi_confirmation_text(multi_txs), reply_markup=confirm_multi_transaction_keyboard())
        return

    kb = new_category_keyboard(data["new_cat_name"]) if data.get("is_new_cat") else confirm_transaction_keyboard()
    await message.answer(build_confirmation_text(data), reply_markup=kb)


@router.callback_query(F.data == "txedit:desc")
async def edit_desc_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditTransaction.editing_description)
    await callback.message.edit_text(
        "📝 Введіть новий опис:",
        reply_markup=back_keyboard("txedit:back"),
    )
    await callback.answer()


@router.message(EditTransaction.editing_description)
async def edit_desc_input(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    await state.update_data(description=desc)
    await state.set_state(None)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx]["description"] = desc
        await state.update_data(multi_txs=multi_txs)
        await message.answer(build_multi_confirmation_text(multi_txs), reply_markup=confirm_multi_transaction_keyboard())
        return

    kb = new_category_keyboard(data["new_cat_name"]) if data.get("is_new_cat") else confirm_transaction_keyboard()
    await message.answer(build_confirmation_text(data), reply_markup=kb)


@router.callback_query(F.data == "txedit:category")
async def edit_category_prompt(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    data = await state.get_data()
    tx_type = data.get("tx_type", "expense")
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category).where(
                and_(Category.user_id == db_user.id, Category.type == tx_type)
            )
        )
        cats = res.scalars().all()

    await callback.message.edit_text(
        "🏷 Виберіть категорію:",
        reply_markup=categories_keyboard(cats, back_cb="txedit:back"),
    )
    await callback.answer()


@router.callback_query(F.data == "txedit:new_cat")
async def edit_new_cat_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(EditTransaction.creating_category_name)
    await callback.message.edit_text(
        "📝 Введіть назву нової категорії:",
        reply_markup=back_keyboard("txedit:back"),
    )
    await callback.answer()


@router.message(EditTransaction.creating_category_name)
async def edit_new_cat_input(message: Message, db_user: User, state: FSMContext) -> None:
    cat_name = (message.text or "").strip()[:50]
    if not cat_name:
        await message.answer("Введіть назву категорії:")
        return

    data = await state.get_data()
    tx_type = data.get("tx_type", "expense")

    async with AsyncSessionLocal() as db:
        cat = Category(user_id=db_user.id, name=cat_name, type=tx_type)
        db.add(cat)
        await db.commit()
        await db.refresh(cat)

    await state.update_data(category_id=cat.id, category_name=cat_name, is_new_cat=False)
    await state.set_state(None)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx]["category_id"] = cat.id
        multi_txs[idx]["category_name"] = cat_name
        multi_txs[idx]["is_new_cat"] = False
        await state.update_data(multi_txs=multi_txs)
        await message.answer(build_multi_confirmation_text(multi_txs), reply_markup=confirm_multi_transaction_keyboard())
        return

    kb = confirm_transaction_keyboard()
    await message.answer(build_confirmation_text(data), reply_markup=kb)


@router.callback_query(F.data == "txedit:account")
async def edit_account_prompt(callback: CallbackQuery, db_user: User) -> None:
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = res.scalars().all()
    await callback.message.edit_text(
        "🏦 Виберіть рахунок:",
        reply_markup=tx_account_select_keyboard(accounts),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("txacc:"))
async def account_picked_for_tx(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    new_acc_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Account).where(and_(Account.id == new_acc_id, Account.user_id == db_user.id))
        )
        new_acc = res.scalar_one_or_none()
    if not new_acc:
        await callback.answer("Рахунок не знайдено")
        return
    await state.update_data(account_id=new_acc_id, account_name=new_acc.name)
    await state.set_state(None)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx]["account_id"] = new_acc_id
        multi_txs[idx]["account_name"] = new_acc.name
        await state.update_data(multi_txs=multi_txs)
        await callback.message.edit_text(
            build_multi_confirmation_text(multi_txs),
            reply_markup=confirm_multi_transaction_keyboard(),
        )
        await callback.answer()
        return

    kb = new_category_keyboard(data["new_cat_name"]) if data.get("is_new_cat") else confirm_transaction_keyboard()
    await callback.message.edit_text(build_confirmation_text(data), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("catpick:"))
async def category_picked(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    cat_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category).where(and_(Category.id == cat_id, Category.user_id == db_user.id))
        )
        cat = res.scalar_one_or_none()

    if not cat:
        await callback.answer("Категорію не знайдено")
        return

    await state.update_data(
        category_id=cat.id,
        category_name=cat.name,
        is_new_cat=False,
        new_cat_name="",
    )
    await state.set_state(None)
    data = await state.get_data()

    if data.get("multi_editing"):
        idx = data["multi_editing_index"]
        multi_txs = data["multi_txs"]
        multi_txs[idx]["category_id"] = cat.id
        multi_txs[idx]["category_name"] = cat.name
        multi_txs[idx]["is_new_cat"] = False
        await state.update_data(multi_txs=multi_txs)
        await callback.message.edit_text(
            build_multi_confirmation_text(multi_txs),
            reply_markup=confirm_multi_transaction_keyboard(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(build_confirmation_text(data), reply_markup=confirm_transaction_keyboard())
    await callback.answer()


# ────────────────────────────────────────────────────────────────
# Перегляд і видалення транзакції
# ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tx:view:"))
async def view_transaction(callback: CallbackQuery, db_user: User) -> None:
    from app.models import Transaction, Category
    from bot.utils.date_utils import fmt_date
    tx_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Transaction).where(
                and_(Transaction.id == tx_id, Transaction.user_id == db_user.id)
            )
        )
        tx = res.scalar_one_or_none()
        cat_name = "—"
        if tx and tx.category_id:
            cat_res = await db.execute(select(Category).where(Category.id == tx.category_id))
            cat = cat_res.scalar_one_or_none()
            cat_name = cat.name if cat else "—"

    if not tx:
        await callback.answer("Транзакцію не знайдено")
        return

    type_emoji = {"expense": "➖", "income": "➕", "transfer": "🔄", "debt_payment": "💳"}
    e = type_emoji.get(tx.type, "💸")
    date_str = tx.date.strftime("%d.%m.%Y %H:%M")
    await callback.message.edit_text(
        f"{e} <b>{tx.type.upper()}</b>\n\n"
        f"💵 Сума: <b>{tx.amount:.2f} {tx.currency}</b> ({tx.amount_uah:.2f} ₴)\n"
        f"📝 Опис: {tx.description or '—'}\n"
        f"🏷 Категорія: {cat_name}\n"
        f"📅 Дата: {date_str}\n"
        f"📌 Джерело: {tx.source}",
        reply_markup=transaction_view_keyboard(tx_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tx:del_confirm:"))
async def tx_del_confirm(callback: CallbackQuery, db_user: User) -> None:
    from app.models import Transaction
    tx_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Transaction).where(
                and_(Transaction.id == tx_id, Transaction.user_id == db_user.id)
            )
        )
        tx = res.scalar_one_or_none()
    label = f"{tx.amount:.0f} {tx.currency} — {tx.description or '?'}" if tx else f"#{tx_id}"
    await callback.message.edit_text(
        f"⚠️ Видалити транзакцію «<b>{label}</b>»?\n\nЦе незворотньо.",
        reply_markup=confirm_delete_keyboard(
            confirm_cb=f"tx:delete:{tx_id}",
            cancel_cb=f"tx:view:{tx_id}",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tx:delete:"))
async def tx_delete(callback: CallbackQuery, db_user: User) -> None:
    from app.models import Transaction, Account
    tx_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Transaction).where(
                and_(Transaction.id == tx_id, Transaction.user_id == db_user.id)
            )
        )
        tx = res.scalar_one_or_none()
        if tx:
            acc = await db.get(Account, tx.account_id)
            if acc:
                if tx.type == "income":
                    acc.balance -= tx.amount
                elif tx.type in ("expense", "debt_payment"):
                    acc.balance += tx.amount
            await db.delete(tx)
            await db.commit()

    await callback.answer("✅ Транзакцію видалено")
    await callback.message.edit_text(
        "✅ Транзакцію видалено.",
        reply_markup=back_keyboard("menu:transactions"),
    )
