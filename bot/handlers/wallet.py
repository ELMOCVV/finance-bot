"""Витрати з Apple Wallet у боті — покроково, з мінімумом натискань.

Після POST /api/wallet-tx бекенд (у фоні) викликає send_wallet_tx_message:
  Крок 0 (лише нова картка) — куди відносити картку: рахунок або «➕ Новий рахунок»
         (діалог назва → баланс).
  Крок 1 — «Що купив?»: власник пише текст або надсилає фото чека, і Claude
         розкладає позиції за категоріями (одна категорія — зберігаємо одразу,
         кілька — розкладка + «✅ Зберегти»; витрата ділиться на кілька). Або
         одним натиском обирає категорію: підказана (запамʼятована для продавця →
         словник → Claude Haiku) — першою з ⭐; вибір запамʼятовується за продавцем.
         «➕ Нова категорія» — назва (можна з емодзі) → категорія створюється й застосовується.
         Текст/чек продавця не запамʼятовують — категорію визначає, що куплено.
  Підсумок — «✅ категорія — коментар» і «✏️ Змінити» (повернутися до кроку 1).
Текст власника, поки витрата чекає на крок 1, вважається описом цієї витрати
(FSM WalletFlow, привʼязано до останньої витрати).
Якщо рахунків немає зовсім — send_wallet_pending_message пропонує створити
рахунок тим самим діалогом і після цього записує відкладену витрату.

/cards — перегляд і скидання привʼязок карток.
Кнопки обробляються лише для власника (WALLET_OWNER_TG_ID).
"""
import base64
import html
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, and_

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import User, Account, Category, Transaction, WalletCard, WalletPending
from app.services.transaction_service import (
    create_transaction_record, delete_transaction_record,
    change_transaction_category, move_transaction_account,
)
from app.services.wallet_service import (
    WALLET_SOURCE, bind_card, get_card_binding, get_remembered_category_id,
    normalize_key, pick_category, remember_merchant_category, split_by_category,
)
from bot.states import WalletFlow, WalletNewAccount
from bot.utils.fsm_edit import HOST_MID_KEY

logger = logging.getLogger(__name__)
router = Router()

_CURRENCY_SYMBOLS = {"UAH": "₴", "EUR": "€", "USD": "$"}


# ── Утиліти ───────────────────────────────────────────────────────────────────

def _owner_tg_id() -> int | None:
    try:
        return int(settings.WALLET_OWNER_TG_ID)
    except ValueError:
        return None


def _is_owner(tg_user_id: int | None) -> bool:
    owner = _owner_tg_id()
    return owner is not None and tg_user_id == owner


def fmt_amount(amount: float, currency: str) -> str:
    """112.6, "UAH" → "112,60 ₴"; 1250.5 → "1 250,50 ₴"."""
    num = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{num} {_CURRENCY_SYMBOLS.get(currency, currency)}"


def _headline(amount: float, currency: str, merchant: str | None) -> str:
    return f"💳 <b>{fmt_amount(amount, currency)}</b> — {html.escape(merchant or 'Без названия')}"


def _note_sep(merchant: str | None) -> str:
    return f"{merchant or 'Без названия'} — "


def get_note(tx: Transaction) -> str | None:
    """Коментар зберігається в description після «продавець — »."""
    prefix = _note_sep(tx.merchant)
    if tx.description and tx.description.startswith(prefix):
        return tx.description[len(prefix):] or None
    return None


def set_note(tx: Transaction, note: str | None) -> None:
    if note:
        prefix = _note_sep(tx.merchant)
        tx.description = (prefix + note)[:512]
    else:
        tx.description = tx.merchant


async def _expense_categories(db, user_id: int) -> list[Category]:
    return (await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.type == "expense"))
        .order_by(Category.name)
    )).scalars().all()


def _cat_label(cat: Category | None) -> str:
    return html.escape(f"{cat.icon or ''} {cat.name}".strip()) if cat else "Без категории"


async def build_tx_view(db, tx: Transaction) -> tuple[str, InlineKeyboardMarkup | None]:
    """Повідомлення про витрату з Wallet — залежно від кроку.

    Крок 0 (нова картка): вибір рахунку. Крок 1 (status=pending): «що купив?» +
    сітка категорій, підказана — першою з ⭐. Підсумок (confirmed): категорія й «✏️ Змінити».
    """
    account = await db.get(Account, tx.account_id)
    acc_name = html.escape(account.name) if account else "—"
    headline = _headline(tx.amount, tx.currency, tx.merchant)
    b = InlineKeyboardBuilder()

    if tx.card and not await get_card_binding(db, tx.user_id, tx.card):
        accs = (await db.execute(
            select(Account).where(Account.user_id == tx.user_id).order_by(Account.id)
        )).scalars().all()
        # Рахунок, підібраний автопідбором (на ньому зараз витрата), — першим
        accs = sorted(accs, key=lambda a: a.id != tx.account_id)
        for acc in accs:
            label = f"⭐ {acc.name} (подсказка)" if acc.id == tx.account_id else acc.name
            b.row(InlineKeyboardButton(text=label[:60], callback_data=f"wtx:bind:{tx.id}:{acc.id}"))
        b.row(InlineKeyboardButton(text="➕ Новый счёт", callback_data=f"wtx:new:{tx.id}"))
        b.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"wtx:del:{tx.id}"))
        text = (f"{headline}\n\n💳 Карта «{html.escape(tx.card)}» ещё не привязана к счёту. "
                f"Куда относить её расходы?")
        return text, b.as_markup()

    category = await db.get(Category, tx.category_id) if tx.category_id else None
    note = get_note(tx)

    if tx.status == "confirmed":
        lines = [f"{headline} · {acc_name}", f"✅ {_cat_label(category)}"]
        if note:
            lines[-1] += f" — {html.escape(note)}"
        b.row(InlineKeyboardButton(text="✏️ Изменить", callback_data=f"wtx:edit:{tx.id}"))
        return "\n".join(lines), b.as_markup()

    cats = sorted(await _expense_categories(db, tx.user_id), key=lambda c: c.id != tx.category_id)
    for c in cats:
        star = "⭐ " if c.id == tx.category_id else ""
        b.button(text=f"{star}{c.icon or ''} {c.name}".strip()[:40], callback_data=f"wtx:sc:{tx.id}:{c.id}")
    b.adjust(2)
    b.row(
        InlineKeyboardButton(text="➕ Новая категория", callback_data=f"wtx:newcat:{tx.id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"wtx:del:{tx.id}"),
    )
    lines = [
        f"{headline} · {acc_name}",
        "",
        "✍️ <b>Что купил?</b> Напиши (напр. «хлеб, молоко 300, сигареты 150») "
        "или пришли фото чека — разложу по категориям.",
        "Или просто выбери категорию:",
    ]
    if note:
        lines.insert(1, f"💬 {html.escape(note)}")
    return "\n".join(lines), b.as_markup()


def _pending_view(p: WalletPending) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"{_headline(p.amount, p.currency, p.merchant)}\n\n"
        f"У тебя ещё нет счетов, поэтому расход отложен. "
        f"Создай счёт — и я сразу его запишу."
    )
    if p.card:
        text += f"\nКарта «{html.escape(p.card)}» будет привязана к нему."
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Новый счёт", callback_data=f"wpend:new:{p.id}"))
    return text, b.as_markup()


# ── Очікування «що купив» (текст або фото) ───────────────────────────────────

def _owner_state(bot, chat_id: int) -> FSMContext:
    """FSM власника в чаті з ботом — той самий ключ, що формує Dispatcher."""
    from bot.main import dp
    return FSMContext(storage=dp.storage, key=StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=chat_id))


async def _await_input(state: FSMContext, tx: Transaction, host_mid: int | None) -> None:
    """Крок 1: наступний текст або фото власника описує цю витрату.
    Не-pending або ще не привʼязана картка — нічого не чекаємо."""
    await state.clear()
    if tx.status != "pending" or host_mid is None:
        return
    await state.set_state(WalletFlow.waiting_input)
    await state.update_data(w_tx_id=tx.id, **{HOST_MID_KEY: host_mid})


async def _release_if_current(state: FSMContext, tx_id: int) -> None:
    if (await state.get_data()).get("w_tx_id") == tx_id:
        await state.clear()


# ── Надсилання (викликається з бекенду у фоні) ───────────────────────────────

async def send_wallet_tx_message(chat_id: int, tx_id: int) -> None:
    from bot.main import bot
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id)
        if not tx:
            return
        text, markup = await build_tx_view(db, tx)
        bound = not tx.card or await get_card_binding(db, tx.user_id, tx.card) is not None
    sent = await bot.send_message(chat_id, text, reply_markup=markup)
    if not bound:
        return
    state = _owner_state(bot, chat_id)
    current = await state.get_state()
    # Не перебиваємо інший діалог (напр. створення рахунку) — тоді лише кнопки
    if current is None or current.startswith(f"{WalletFlow.__name__}:"):
        await _await_input(state, tx, sent.message_id)


async def send_wallet_pending_message(chat_id: int, pending_id: int) -> None:
    from bot.main import bot
    async with AsyncSessionLocal() as db:
        p = await db.get(WalletPending, pending_id)
        if not p:
            return
        text, markup = _pending_view(p)
    await bot.send_message(chat_id, text, reply_markup=markup)


async def _load_tx(db, callback: CallbackQuery, db_user: User, tx_id: int) -> Transaction | None:
    res = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == tx_id, Transaction.user_id == db_user.id,
                 Transaction.source == WALLET_SOURCE)
        )
    )
    tx = res.scalar_one_or_none()
    if not tx:
        await callback.answer("Расход не найден", show_alert=True)
    return tx


async def _show_tx(callback: CallbackQuery, db, tx: Transaction) -> None:
    text, markup = await build_tx_view(db, tx)
    await callback.message.edit_text(text, reply_markup=markup)


# ── Кнопки під витратою ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("wtx:"))
async def wallet_tx_action(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()  # чужі callback ігноруємо
        return
    parts = callback.data.split(":")
    action, tx_id = parts[1], int(parts[2])

    async with AsyncSessionLocal() as db:
        tx = await _load_tx(db, callback, db_user, tx_id)
        if not tx:
            return

        if action == "sc":
            # Категорія одним натиском = готово; продавця запамʼятовуємо
            cat = (await db.execute(
                select(Category).where(and_(Category.id == int(parts[3]), Category.user_id == db_user.id))
            )).scalar_one_or_none()
            if not cat:
                await callback.answer("Категория не найдена", show_alert=True)
                return
            await change_transaction_category(db, tx, cat.id)
            await remember_merchant_category(db, db_user.id, tx.merchant, cat.id)
            tx.status = "confirmed"
            await db.commit()
            await _release_if_current(state, tx.id)
            await _show_tx(callback, db, tx)
            await callback.answer(f"✅ {cat.name}")

        elif action == "edit":
            tx.status = "pending"
            await db.commit()
            await _show_tx(callback, db, tx)
            await _await_input(state, tx, callback.message.message_id)
            await callback.answer()

        elif action == "del":
            headline = _headline(tx.amount, tx.currency, tx.merchant)
            await delete_transaction_record(db, tx)
            await db.commit()
            await _release_if_current(state, tx_id)
            await callback.message.edit_text(f"<s>{headline}</s>\n\n🗑 Удалено", reply_markup=None)
            await callback.answer("Удалено")

        elif action == "bind":
            acc = (await db.execute(
                select(Account).where(and_(Account.id == int(parts[3]), Account.user_id == db_user.id))
            )).scalar_one_or_none()
            if not acc or not tx.card:
                await callback.answer("Счёт не найден", show_alert=True)
                return
            await bind_card(db, db_user.id, tx.card, acc.id)
            await move_transaction_account(db, tx, acc)
            await db.commit()
            await _show_tx(callback, db, tx)
            await _await_input(state, tx, callback.message.message_id)
            await callback.answer(f"Карта привязана к «{acc.name}»")

        elif action == "new":
            await _start_new_account(callback, state, "tx", tx.id, tx.card, tx.currency)

        elif action == "newcat":
            await state.clear()
            await state.set_state(WalletFlow.new_category)
            await state.update_data(w_tx_id=tx.id, **{HOST_MID_KEY: callback.message.message_id})
            b = InlineKeyboardBuilder()
            b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="wncat:cancel"))
            await callback.message.edit_text(
                f"{_headline(tx.amount, tx.currency, tx.merchant)}\n\n"
                f"➕ Напиши название новой категории — можно с эмодзи в начале (напр. «🚬 Табак»):",
                reply_markup=b.as_markup(),
            )
            await callback.answer()

        else:
            await callback.answer()


@router.callback_query(F.data.startswith("wpend:new:"))
async def wallet_pending_new_account(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    async with AsyncSessionLocal() as db:
        p = await db.get(WalletPending, int(callback.data.split(":")[2]))
    if not p or p.user_id != db_user.id:
        await callback.answer("Расход уже обработан", show_alert=True)
        return
    await _start_new_account(callback, state, "pending", p.id, p.card, p.currency)


# ── «Що купив»: текст або фото чека → розкладка за категоріями ───────────────

async def _download_image(message: Message) -> tuple[str, str] | None:
    """(base64, media_type) з фото або зображення-документа; None — якщо це не зображення."""
    if message.photo:
        file_id, media_type = message.photo[-1].file_id, "image/jpeg"
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id, media_type = message.document.file_id, message.document.mime_type
    else:
        return None
    file = await message.bot.get_file(file_id)
    data = await message.bot.download_file(file.file_path)
    return base64.b64encode(data.read()).decode(), media_type


def _split_view(
    tx: Transaction, groups: list[dict], cats: dict[int, Category], from_photo: bool = False,
) -> tuple[str, InlineKeyboardMarkup]:
    title = "🧾 <b>Чек разложен так:</b>" if from_photo else "🤖 <b>Разложил так:</b>"
    lines = [_headline(tx.amount, tx.currency, tx.merchant), "", title]
    for g in groups:
        if g["new_category"]:
            label = f"🆕 {html.escape((g.get('new_icon') or '') + ' ' + g['new_category']).strip()}"
        else:
            label = _cat_label(cats.get(g["category_id"] or tx.category_id))
        names = ", ".join(g["names"])
        names = f" ({html.escape(names[:80] + ('…' if len(names) > 80 else ''))})" if names else ""
        approx = "≈" if g.get("estimated") else ""
        lines.append(f"• {label} — <b>{approx}{fmt_amount(g['amount'], tx.currency)}</b>{names}")
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Сохранить", callback_data="wrc:ok"),
        InlineKeyboardButton(text="✏️ Вручную", callback_data="wrc:manual"),
    )
    return "\n".join(lines), b.as_markup()


@router.message(WalletFlow.waiting_input, ~F.text.startswith("/"))
async def wallet_purchase_input(message: Message, db_user: User, state: FSMContext) -> None:
    text = (message.text or message.caption or "").strip()
    image = None if message.text else await _download_image(message)
    if not text and not image:
        await message.answer("Напиши, что купил, или пришли фото чека.")
        return
    tx_id = (await state.get_data()).get("w_tx_id")
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id) if tx_id else None
        if not tx or tx.user_id != db_user.id or tx.status != "pending":
            await state.clear()
            await message.answer("Этот расход уже обработан.")
            return
        cats = await _expense_categories(db, db_user.id)

    headline = _headline(tx.amount, tx.currency, tx.merchant)
    await _edit_host(message.bot, message.chat.id, state,
                     f"{headline}\n\n{'📸 Распознаю чек' if image else '🤖 Раскладываю'}...")
    from app.services.claude_service import claude_service
    cat_list = [{"id": c.id, "name": c.name} for c in cats]
    if image:
        parsed = await claude_service.parse_receipt_items(image[0], cat_list, media_type=image[1])
    else:
        parsed = await claude_service.parse_purchase_text(text, tx.amount, tx.currency, cat_list)
    groups = [] if "error" in parsed else split_by_category(parsed.get("items") or [], tx.amount, cats)

    if not groups:
        logger.info("Wallet input not parsed (tx_id=%s): %s", tx.id, parsed.get("error"))
        async with AsyncSessionLocal() as db:
            view, markup = await build_tx_view(db, tx)
        what = "чек. Попробуй более чёткое фото" if image else "описание. Попробуй иначе"
        await _edit_host(message.bot, message.chat.id, state, f"❌ Не понял {what} или выбери категорию.\n\n{view}", markup)
        return

    note = text or None
    if len(groups) == 1:
        # Одна категорія — зберігаємо одразу, без підтвердження
        await _save_groups(message.bot, message.chat.id, db_user, state, tx.id, tx.amount, groups, note)
        return
    await state.set_state(WalletFlow.confirming)
    await state.update_data(w_split=groups, w_amount=tx.amount, w_note=note)
    view, markup = _split_view(tx, groups, {c.id: c for c in cats}, from_photo=bool(image))
    await _edit_host(message.bot, message.chat.id, state, view, markup)


async def _category_for_group(db, user_id: int, g: dict, fallback_id: int | None) -> int | None:
    if g["category_id"]:
        return g["category_id"]
    if not g["new_category"]:
        return fallback_id
    cat = Category(user_id=user_id, name=g["new_category"], type="expense", icon=g.get("new_icon") or "🏷")
    db.add(cat)
    await db.flush()
    return cat.id


async def _apply_split(
    db, db_user: User, tx: Transaction, groups: list[dict], note: str | None = None,
) -> list[Transaction]:
    """Одна група — змінюємо категорію й коментар на місці; кілька — видаляємо витрату
    й створюємо по одній на групу (баланс рахунку в сумі не змінюється).
    note — коментар для однієї групи (інакше — назви позицій)."""
    new_cat_ids: dict[str, int] = {}

    async def cat_id(g: dict) -> int | None:
        key = g["new_category"] or ""
        if key and key in new_cat_ids:
            return new_cat_ids[key]
        cid = await _category_for_group(db, db_user.id, g, tx.category_id)
        if key:
            new_cat_ids[key] = cid
        return cid

    if len(groups) == 1:
        g = groups[0]
        await change_transaction_category(db, tx, await cat_id(g))
        if note or g["names"]:
            set_note(tx, note or ", ".join(g["names"]))
        tx.status = "confirmed"
        return [tx]

    account = await db.get(Account, tx.account_id)
    merchant = tx.merchant
    base = dict(
        user_id=tx.user_id, account=account, type=tx.type, currency=tx.currency, date=tx.date,
        source=WALLET_SOURCE, merchant=merchant, card=tx.card,
    )
    await delete_transaction_record(db, tx)
    parts = []
    for g in groups:
        part = await create_transaction_record(
            db, amount=g["amount"], category_id=await cat_id(g),
            description=(_note_sep(merchant) + ", ".join(g["names"]))[:512] if g["names"] else merchant,
            **base,
        )
        part.status = "confirmed"
        parts.append(part)
    return parts


async def _save_groups(
    bot, chat_id: int, db_user: User, state: FSMContext, tx_id: int, amount: float,
    groups: list[dict], note: str | None,
) -> None:
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id)
        if not tx or tx.user_id != db_user.id or tx.amount != amount:
            await _edit_host(bot, chat_id, state, "Расход уже изменён — разбивка отменена.")
            await state.clear()
            return
        headline = _headline(tx.amount, tx.currency, tx.merchant)
        account = await db.get(Account, tx.account_id)
        parts = await _apply_split(db, db_user, tx, groups, note)
        await db.commit()
        if len(parts) == 1:
            text, markup = await build_tx_view(db, parts[0])
        else:
            lines = [f"{headline} · {html.escape(account.name) if account else '—'}",
                     f"✅ Разбито на {len(parts)}:"]
            for part in parts:
                cat = await db.get(Category, part.category_id) if part.category_id else None
                lines.append(f"• {_cat_label(cat)} — <b>{fmt_amount(part.amount, part.currency)}</b>")
            text, markup = "\n".join(lines), None
        logger.info("Wallet split applied: tx_id=%s parts=%s", tx_id, [p.id for p in parts])
    await _edit_host(bot, chat_id, state, text, markup)
    await state.clear()


@router.callback_query(F.data.startswith("wrc:"))
async def wallet_split_buttons(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if "w_split" not in data:
        await callback.answer("Диалог устарел", show_alert=True)
        return
    chat_id = callback.message.chat.id
    if callback.data == "wrc:ok":
        await _save_groups(callback.bot, chat_id, db_user, state, data["w_tx_id"], data["w_amount"],
                           data["w_split"], data.get("w_note"))
        await callback.answer("Сохранено")
        return
    # ✏️ Вручну — назад до кроку 1
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, data["w_tx_id"])
        if not tx:
            await state.clear()
            await callback.answer("Расход не найден", show_alert=True)
            return
        text, markup = await build_tx_view(db, tx)
    await _edit_host(callback.bot, chat_id, state, text, markup)
    await _await_input(state, tx, data.get(HOST_MID_KEY))
    await callback.answer()


# ── «➕ Нова категорія» з кроку 1 ───────────────────────────────────────────

def split_icon(text: str) -> tuple[str | None, str]:
    """«🚬 Тютюн» → ("🚬", "Тютюн"); «Тютюн» → (None, "Тютюн")."""
    text = " ".join(text.split())
    head, _, rest = text.partition(" ")
    if rest and not any(ch.isalnum() for ch in head):
        return head[:16], rest
    return None, text


async def _find_or_create_category(db, user_id: int, name: str, icon: str | None) -> Category:
    for c in await _expense_categories(db, user_id):
        if normalize_key(c.name, 128) == normalize_key(name, 128):
            return c
    cat = Category(user_id=user_id, name=name[:128], type="expense", icon=icon or "🏷")
    db.add(cat)
    await db.flush()
    return cat


@router.message(WalletFlow.new_category, F.text, ~F.text.startswith("/"))
async def wallet_new_category_name(message: Message, db_user: User, state: FSMContext) -> None:
    icon, name = split_icon(message.text)
    if not name:
        await message.answer("Название пустое. Напиши название категории или нажми «Отмена».")
        return
    tx_id = (await state.get_data()).get("w_tx_id")
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id) if tx_id else None
        if not tx or tx.user_id != db_user.id:
            await state.clear()
            await message.answer("Этот расход уже обработан.")
            return
        cat = await _find_or_create_category(db, db_user.id, name, icon)
        await change_transaction_category(db, tx, cat.id)
        await remember_merchant_category(db, db_user.id, tx.merchant, cat.id)
        tx.status = "confirmed"
        await db.commit()
        text, markup = await build_tx_view(db, tx)
    logger.info("Wallet: category %r (id=%s) for tx_id=%s", cat.name, cat.id, tx_id)
    await _edit_host(message.bot, message.chat.id, state, text, markup)
    await state.clear()


@router.callback_query(F.data == "wncat:cancel")
async def wallet_new_category_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, data["w_tx_id"]) if data.get("w_tx_id") else None
        if not tx:
            await state.clear()
            await callback.answer("Диалог устарел", show_alert=True)
            return
        text, markup = await build_tx_view(db, tx)
    await _edit_host(callback.bot, callback.message.chat.id, state, text, markup)
    await _await_input(state, tx, data.get(HOST_MID_KEY))
    await callback.answer()


# ── Діалог «➕ Новий рахунок» ────────────────────────────────────────────────

async def _start_new_account(
    callback: CallbackQuery, state: FSMContext, target: str, target_id: int,
    card: str | None, currency: str,
) -> None:
    await state.clear()
    await state.set_state(WalletNewAccount.waiting_name)
    await state.update_data(
        w_target=target, w_target_id=target_id, w_card=card, w_currency=currency,
        **{HOST_MID_KEY: callback.message.message_id},
    )
    b = InlineKeyboardBuilder()
    if card:
        b.row(InlineKeyboardButton(text=f"✏️ {card}"[:60], callback_data="wna:usecard"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="wna:cancel"))
    await callback.message.edit_text(
        "➕ <b>Новый счёт</b>\n\nНапиши название счёта" + (" или выбери название карты:" if card else ":"),
        reply_markup=b.as_markup(),
    )
    await callback.answer()


async def _edit_host(bot, chat_id: int, state: FSMContext, text: str, markup=None) -> None:
    mid = (await state.get_data()).get(HOST_MID_KEY)
    if mid:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=markup)
            return
        except Exception as e:
            logger.info("Wallet: host edit failed (%s), sending new message", e.__class__.__name__)
    await bot.send_message(chat_id, text, reply_markup=markup)


async def _ask_balance(bot, chat_id: int, state: FSMContext, name: str) -> None:
    await state.update_data(w_name=name)
    await state.set_state(WalletNewAccount.waiting_balance)
    data = await state.get_data()
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⏭ Пропустить (0)", callback_data="wna:skip"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="wna:cancel"))
    await _edit_host(
        bot, chat_id, state,
        f"➕ Счёт «{html.escape(name)}» ({data['w_currency']})\n\n"
        f"Введи текущий баланс счёта — расход будет списан с него:",
        b.as_markup(),
    )


@router.message(WalletNewAccount.waiting_name)
async def wallet_new_account_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("Название не может быть пустым. Попробуй ещё раз:")
        return
    await _ask_balance(message.bot, message.chat.id, state, name)


@router.message(WalletNewAccount.waiting_balance)
async def wallet_new_account_balance(message: Message, db_user: User, state: FSMContext) -> None:
    raw = (message.text or "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        balance = float(raw)
    except ValueError:
        await message.answer("Введи число, например <i>1500</i> или <i>1500,50</i>:")
        return
    await _finish_new_account(message.bot, message.chat.id, db_user, state, balance)


@router.callback_query(F.data.startswith("wna:"))
async def wallet_new_account_buttons(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if "w_target" not in data:
        await callback.answer("Диалог устарел", show_alert=True)
        return
    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    if action == "usecard" and data.get("w_card"):
        await _ask_balance(callback.bot, chat_id, state, data["w_card"])
    elif action == "skip":
        await _finish_new_account(callback.bot, chat_id, db_user, state, 0.0)
    elif action == "cancel":
        await _restore_view(callback.bot, chat_id, state, data)
        await state.clear()
    await callback.answer()


async def _restore_view(bot, chat_id: int, state: FSMContext, data: dict) -> None:
    """Повертає вихідне повідомлення (витрата або відкладена витрата)."""
    async with AsyncSessionLocal() as db:
        if data["w_target"] == "tx":
            tx = await db.get(Transaction, data["w_target_id"])
            if tx:
                text, markup = await build_tx_view(db, tx)
                await _edit_host(bot, chat_id, state, text, markup)
                return
        else:
            p = await db.get(WalletPending, data["w_target_id"])
            if p:
                text, markup = _pending_view(p)
                await _edit_host(bot, chat_id, state, text, markup)
                return
    await _edit_host(bot, chat_id, state, "Расход уже обработан.")


async def _finish_new_account(bot, chat_id: int, db_user: User, state: FSMContext, balance: float) -> None:
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        has_accounts = (await db.execute(
            select(Account.id).where(Account.user_id == db_user.id).limit(1)
        )).first() is not None
        acc = Account(
            user_id=db_user.id, name=data["w_name"], currency=data["w_currency"],
            balance=balance, is_default=not has_accounts, keywords=[],
        )
        db.add(acc)
        await db.flush()
        card = data.get("w_card")
        if card:
            await bind_card(db, db_user.id, card, acc.id)

        tx = None
        if data["w_target"] == "tx":
            tx = await db.get(Transaction, data["w_target_id"])
            if tx and tx.user_id == db_user.id:
                await move_transaction_account(db, tx, acc)
        else:
            p = await db.get(WalletPending, data["w_target_id"])
            if p and p.user_id == db_user.id:
                cats = (await db.execute(
                    select(Category).where(and_(Category.user_id == db_user.id, Category.type == "expense"))
                )).scalars().all()
                category = pick_category(
                    p.merchant, cats, await get_remembered_category_id(db, db_user.id, p.merchant),
                )
                tx = await create_transaction_record(
                    db, user_id=db_user.id, account=acc, type="expense",
                    amount=p.amount, currency=p.currency,
                    category_id=category.id if category else None,
                    description=p.merchant, source=WALLET_SOURCE,
                    merchant=p.merchant, card=p.card,
                )
                tx.status = "pending"
                await db.delete(p)
        await db.commit()
        logger.info("Wallet: created account_id=%s card_bound=%s tx_id=%s",
                    acc.id, bool(card), tx.id if tx else None)
        if tx:
            text, markup = await build_tx_view(db, tx)
        else:
            text, markup = f"✅ Счёт «{html.escape(acc.name)}» создан.", None
    host_mid = data.get(HOST_MID_KEY)
    await _edit_host(bot, chat_id, state, text, markup)
    await state.clear()
    if tx:
        await _await_input(state, tx, host_mid)


# ── /cards: привʼязки карток ─────────────────────────────────────────────────

async def _cards_view(db_user: User) -> tuple[str, InlineKeyboardMarkup | None]:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(WalletCard, Account.name)
            .join(Account, Account.id == WalletCard.account_id)
            .where(WalletCard.user_id == db_user.id)
            .order_by(WalletCard.card_name)
        )).all()
    if not rows:
        return ("💳 Привязок карт Apple Wallet ещё нет.\n"
                "Они появятся, когда ты выберешь счёт для новой карты."), None
    lines = ["💳 <b>Привязки карт Apple Wallet:</b>\n"]
    b = InlineKeyboardBuilder()
    for card, acc_name in rows:
        lines.append(f"• {html.escape(card.card_name)} → {html.escape(acc_name)}")
        b.row(InlineKeyboardButton(text=f"❌ {card.card_name}"[:60], callback_data=f"wcard:del:{card.id}"))
    b.row(InlineKeyboardButton(text="🗑 Сбросить все", callback_data="wcard:all"))
    lines.append("\nПосле сброса бот снова спросит счёт при следующем расходе с карты.")
    return "\n".join(lines), b.as_markup()


@router.message(Command("cards"))
async def cmd_cards(message: Message, db_user: User) -> None:
    text, markup = await _cards_view(db_user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("wcard:"))
async def wallet_cards_reset(callback: CallbackQuery, db_user: User) -> None:
    parts = callback.data.split(":")
    async with AsyncSessionLocal() as db:
        q = select(WalletCard).where(WalletCard.user_id == db_user.id)
        if parts[1] == "del":
            q = q.where(WalletCard.id == int(parts[2]))
        for row in (await db.execute(q)).scalars().all():
            await db.delete(row)
        await db.commit()
    text, markup = await _cards_view(db_user)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer("Привязка сброшена")
