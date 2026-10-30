"""Підтвердження витрат з Apple Wallet у боті.

Після POST /api/wallet-tx бекенд (у фоні) викликає send_wallet_tx_message —
власник отримує повідомлення з кнопками:
  ✅ Вірно      — status=confirmed, кнопки дій зникають;
  📂 Категорія  — вибір категорії (перерахунок бюджетів + запамʼятовування
                  «продавець → категорія»);
  🗑 Видалити   — видалення з поверненням балансу й бюджету;
  💬 Коментар   — необовʼязковий коментар (description = «продавець — коментар»);
  🧾 Чек        — фото чека → Claude розкладає позиції за категоріями →
                  витрата розбивається на кілька (запамʼятовування продавця не чіпаємо).
Якщо картка ще не привʼязана до рахунку — блок вибору рахунку
(підказаний автопідбором — першим) і «➕ Новий рахунок» (діалог назва → баланс).
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
    pick_category, remember_merchant_category, split_by_category,
)
from bot.states import WalletNewAccount, WalletNote, WalletReceipt
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
    return f"💳 <b>{fmt_amount(amount, currency)}</b> — {html.escape(merchant or 'Без назви')}"


def _note_sep(merchant: str | None) -> str:
    return f"{merchant or 'Без назви'} — "


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


async def build_tx_view(db, tx: Transaction) -> tuple[str, InlineKeyboardMarkup | None]:
    """Текст і кнопки повідомлення про витрату з Wallet."""
    account = await db.get(Account, tx.account_id)
    category = await db.get(Category, tx.category_id) if tx.category_id else None
    lines = [
        _headline(tx.amount, tx.currency, tx.merchant),
        f"Категорія: {html.escape(category.name) if category else 'Без категорії'}"
        f" · Рахунок: {html.escape(account.name) if account else '—'}",
    ]
    note = get_note(tx)
    if note:
        lines.append(f"💬 {html.escape(note)}")
    b = InlineKeyboardBuilder()
    if tx.status == "confirmed":
        lines.append("\n✅ Підтверджено")
    else:
        b.row(
            InlineKeyboardButton(text="✅ Вірно", callback_data=f"wtx:ok:{tx.id}"),
            InlineKeyboardButton(text="📂 Категорія", callback_data=f"wtx:cat:{tx.id}"),
            InlineKeyboardButton(text="🗑 Видалити", callback_data=f"wtx:del:{tx.id}"),
        )
    b.row(
        InlineKeyboardButton(text="💬 Коментар", callback_data=f"wtx:note:{tx.id}"),
        InlineKeyboardButton(text="🧾 Чек", callback_data=f"wtx:rcpt:{tx.id}"),
    )

    if tx.card and not await get_card_binding(db, tx.user_id, tx.card):
        lines.append(
            f"\n💳 Картка «{html.escape(tx.card)}» ще не привʼязана до рахунку. "
            f"Куди відносити її витрати?"
        )
        accs = (await db.execute(
            select(Account).where(Account.user_id == tx.user_id).order_by(Account.id)
        )).scalars().all()
        # Рахунок, підібраний автопідбором (на ньому зараз витрата), — першим
        accs = sorted(accs, key=lambda a: a.id != tx.account_id)
        for acc in accs:
            label = f"⭐ {acc.name} (підказка)" if acc.id == tx.account_id else acc.name
            b.row(InlineKeyboardButton(text=label[:60], callback_data=f"wtx:bind:{tx.id}:{acc.id}"))
        b.row(InlineKeyboardButton(text="➕ Новий рахунок", callback_data=f"wtx:new:{tx.id}"))

    markup = b.as_markup() if b.export() else None
    return "\n".join(lines), markup


def _pending_view(p: WalletPending) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        f"{_headline(p.amount, p.currency, p.merchant)}\n\n"
        f"У тебе ще немає рахунків, тож витрату відкладено. "
        f"Створи рахунок — і я одразу її запишу."
    )
    if p.card:
        text += f"\nКартку «{html.escape(p.card)}» буде привʼязано до нього."
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Новий рахунок", callback_data=f"wpend:new:{p.id}"))
    return text, b.as_markup()


# ── Надсилання (викликається з бекенду у фоні) ───────────────────────────────

async def send_wallet_tx_message(chat_id: int, tx_id: int) -> None:
    from bot.main import bot
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id)
        if not tx:
            return
        text, markup = await build_tx_view(db, tx)
    await bot.send_message(chat_id, text, reply_markup=markup)


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
        await callback.answer("Витрату не знайдено", show_alert=True)
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

        if action == "ok":
            tx.status = "confirmed"
            await db.commit()
            await _show_tx(callback, db, tx)
            await callback.answer("Підтверджено")

        elif action == "back":
            await _show_tx(callback, db, tx)
            await callback.answer()

        elif action == "cat":
            cats = (await db.execute(
                select(Category).where(and_(Category.user_id == db_user.id, Category.type == "expense"))
                .order_by(Category.name)
            )).scalars().all()
            b = InlineKeyboardBuilder()
            for c in cats:
                mark = "• " if c.id == tx.category_id else ""
                b.button(text=f"{mark}{c.icon or ''} {c.name}".strip()[:40], callback_data=f"wtx:sc:{tx.id}:{c.id}")
            b.adjust(2)
            b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"wtx:back:{tx.id}"))
            await callback.message.edit_text(
                f"{_headline(tx.amount, tx.currency, tx.merchant)}\n\n📂 Оберіть категорію:",
                reply_markup=b.as_markup(),
            )
            await callback.answer()

        elif action == "sc":
            cat = (await db.execute(
                select(Category).where(and_(Category.id == int(parts[3]), Category.user_id == db_user.id))
            )).scalar_one_or_none()
            if not cat:
                await callback.answer("Категорію не знайдено", show_alert=True)
                return
            await change_transaction_category(db, tx, cat.id)
            await remember_merchant_category(db, db_user.id, tx.merchant, cat.id)
            await db.commit()
            await _show_tx(callback, db, tx)
            await callback.answer(f"Категорія: {cat.name}")

        elif action == "del":
            headline = _headline(tx.amount, tx.currency, tx.merchant)
            await delete_transaction_record(db, tx)
            await db.commit()
            await callback.message.edit_text(f"<s>{headline}</s>\n\n🗑 Видалено", reply_markup=None)
            await callback.answer("Видалено")

        elif action == "bind":
            acc = (await db.execute(
                select(Account).where(and_(Account.id == int(parts[3]), Account.user_id == db_user.id))
            )).scalar_one_or_none()
            if not acc or not tx.card:
                await callback.answer("Рахунок не знайдено", show_alert=True)
                return
            await bind_card(db, db_user.id, tx.card, acc.id)
            await move_transaction_account(db, tx, acc)
            await db.commit()
            await _show_tx(callback, db, tx)
            await callback.answer(f"Картку привʼязано до «{acc.name}»")

        elif action == "new":
            await _start_new_account(callback, state, "tx", tx.id, tx.card, tx.currency)

        elif action == "note":
            await state.clear()
            await state.set_state(WalletNote.waiting_text)
            await state.update_data(w_tx_id=tx.id, **{HOST_MID_KEY: callback.message.message_id})
            b = InlineKeyboardBuilder()
            if get_note(tx):
                b.row(InlineKeyboardButton(text="🗑 Прибрати коментар", callback_data="wnote:clear"))
            b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="wnote:cancel"))
            await callback.message.edit_text(
                f"{_headline(tx.amount, tx.currency, tx.merchant)}\n\n💬 Напиши коментар до витрати:",
                reply_markup=b.as_markup(),
            )
            await callback.answer()

        elif action == "rcpt":
            await state.clear()
            await state.set_state(WalletReceipt.waiting_photo)
            await state.update_data(w_tx_id=tx.id, **{HOST_MID_KEY: callback.message.message_id})
            b = InlineKeyboardBuilder()
            b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="wrc:cancel"))
            await callback.message.edit_text(
                f"{_headline(tx.amount, tx.currency, tx.merchant)}\n\n"
                f"🧾 Надішли фото чека — розкладу позиції за категоріями "
                f"і розібʼю витрату, якщо там різне (наприклад, продукти й тютюн).",
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
        await callback.answer("Витрату вже оброблено", show_alert=True)
        return
    await _start_new_account(callback, state, "pending", p.id, p.card, p.currency)


# ── 💬 Коментар ──────────────────────────────────────────────────────────────

async def _restore_tx(bot, chat_id: int, state: FSMContext, tx_id: int | None) -> None:
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id) if tx_id else None
        if tx:
            text, markup = await build_tx_view(db, tx)
        else:
            text, markup = "Витрату вже оброблено.", None
    await _edit_host(bot, chat_id, state, text, markup)
    await state.clear()


async def _save_note(bot, chat_id: int, db_user: User, state: FSMContext, note: str | None) -> None:
    tx_id = (await state.get_data()).get("w_tx_id")
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id) if tx_id else None
        if tx and tx.user_id == db_user.id:
            set_note(tx, note)
            await db.commit()
    await _restore_tx(bot, chat_id, state, tx_id)


@router.message(WalletNote.waiting_text, F.text)
async def wallet_note_text(message: Message, db_user: User, state: FSMContext) -> None:
    note = message.text.strip()
    if not note:
        await message.answer("Коментар порожній. Напиши текст або натисни «Скасувати».")
        return
    await _save_note(message.bot, message.chat.id, db_user, state, note)


@router.callback_query(F.data.startswith("wnote:"))
async def wallet_note_buttons(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if "w_tx_id" not in data:
        await callback.answer("Діалог застарів", show_alert=True)
        return
    chat_id = callback.message.chat.id
    if callback.data == "wnote:clear":
        await _save_note(callback.bot, chat_id, db_user, state, None)
        await callback.answer("Коментар прибрано")
    else:
        await _restore_tx(callback.bot, chat_id, state, data["w_tx_id"])
        await callback.answer()


# ── 🧾 Чек → розбивка за категоріями ──────────────────────────────────────────

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


async def _expense_categories(db, user_id: int) -> list[Category]:
    return (await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.type == "expense"))
    )).scalars().all()


def _split_view(tx: Transaction, groups: list[dict], cats: dict[int, Category]) -> tuple[str, InlineKeyboardMarkup]:
    lines = [_headline(tx.amount, tx.currency, tx.merchant), "", "🧾 <b>Чек розпізнано:</b>"]
    for g in groups:
        cat = cats.get(g["category_id"] or tx.category_id)
        if g["new_category"]:
            label = f"🆕 {html.escape(g['new_category'])}"
        else:
            label = html.escape(f"{cat.icon or ''} {cat.name}".strip()) if cat else "Без категорії"
        names = ", ".join(g["names"])
        names = f" ({html.escape(names[:80] + ('…' if len(names) > 80 else ''))})" if names else ""
        lines.append(f"• {label} — <b>{fmt_amount(g['amount'], tx.currency)}</b>{names}")
    b = InlineKeyboardBuilder()
    ok_text = "✅ Розбити" if len(groups) > 1 else "✅ Застосувати"
    b.row(
        InlineKeyboardButton(text=ok_text, callback_data="wrc:ok"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data="wrc:cancel"),
    )
    return "\n".join(lines), b.as_markup()


@router.message(WalletReceipt.waiting_photo)
async def wallet_receipt_photo(message: Message, db_user: User, state: FSMContext) -> None:
    image = await _download_image(message)
    if not image:
        await message.answer("Надішли саме фото чека або натисни «Скасувати».")
        return
    tx_id = (await state.get_data()).get("w_tx_id")
    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, tx_id) if tx_id else None
        if not tx or tx.user_id != db_user.id:
            await _edit_host(message.bot, message.chat.id, state, "Витрату вже оброблено.")
            await state.clear()
            return
        cats = await _expense_categories(db, db_user.id)

    await _edit_host(message.bot, message.chat.id, state,
                     f"{_headline(tx.amount, tx.currency, tx.merchant)}\n\n📸 Розпізнаю чек...")
    from app.services.claude_service import claude_service
    parsed = await claude_service.parse_receipt_items(
        image[0], [{"id": c.id, "name": c.name} for c in cats], media_type=image[1],
    )
    groups = [] if "error" in parsed else split_by_category(parsed.get("items") or [], tx.amount, cats)
    if not groups:
        logger.info("Wallet receipt not parsed (tx_id=%s): %s", tx.id, parsed.get("error"))
        async with AsyncSessionLocal() as db:
            text, markup = await build_tx_view(db, tx)
        await _edit_host(message.bot, message.chat.id, state,
                         f"❌ Не вдалось розпізнати чек. Спробуй чіткіше фото.\n\n{text}", markup)
        await state.clear()
        return

    await state.set_state(WalletReceipt.confirming)
    await state.update_data(w_split=groups, w_amount=tx.amount)
    text, markup = _split_view(tx, groups, {c.id: c for c in cats})
    await _edit_host(message.bot, message.chat.id, state, text, markup)


async def _category_for_group(db, user_id: int, g: dict, fallback_id: int | None) -> int | None:
    if g["category_id"]:
        return g["category_id"]
    if not g["new_category"]:
        return fallback_id
    cat = Category(user_id=user_id, name=g["new_category"], type="expense", icon="🏷")
    db.add(cat)
    await db.flush()
    return cat.id


async def _apply_split(db, db_user: User, tx: Transaction, groups: list[dict]) -> list[Transaction]:
    """Одна група — змінюємо категорію й коментар на місці; кілька — видаляємо витрату
    й створюємо по одній на групу (баланс рахунку в сумі не змінюється)."""
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
        if g["names"]:
            set_note(tx, ", ".join(g["names"]))
        tx.status = "confirmed"
        return [tx]

    account = await db.get(Account, tx.account_id)
    base = dict(
        user_id=tx.user_id, account=account, type=tx.type, currency=tx.currency, date=tx.date,
        source=WALLET_SOURCE, merchant=tx.merchant, card=tx.card,
    )
    await delete_transaction_record(db, tx)
    parts = []
    for g in groups:
        part = await create_transaction_record(
            db, amount=g["amount"], category_id=await cat_id(g),
            description=(_note_sep(tx.merchant) + ", ".join(g["names"]))[:512] if g["names"] else tx.merchant,
            **base,
        )
        part.status = "confirmed"
        parts.append(part)
    return parts


@router.callback_query(F.data.startswith("wrc:"))
async def wallet_receipt_buttons(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if "w_tx_id" not in data:
        await callback.answer("Діалог застарів", show_alert=True)
        return
    chat_id = callback.message.chat.id
    if callback.data != "wrc:ok" or "w_split" not in data:
        await _restore_tx(callback.bot, chat_id, state, data["w_tx_id"])
        await callback.answer()
        return

    async with AsyncSessionLocal() as db:
        tx = await db.get(Transaction, data["w_tx_id"])
        if not tx or tx.user_id != db_user.id or tx.amount != data["w_amount"]:
            await _edit_host(callback.bot, chat_id, state, "Витрату вже змінено — розбивку скасовано.")
            await state.clear()
            await callback.answer()
            return
        headline = _headline(tx.amount, tx.currency, tx.merchant)
        parts = await _apply_split(db, db_user, tx, data["w_split"])
        await db.commit()
        if len(parts) == 1:
            text, markup = await build_tx_view(db, parts[0])
        else:
            lines = [headline, "", f"🧾 Розбито на {len(parts)} витрати:"]
            for part in parts:
                cat = await db.get(Category, part.category_id) if part.category_id else None
                lines.append(f"• {html.escape(cat.name) if cat else 'Без категорії'} — "
                             f"<b>{fmt_amount(part.amount, part.currency)}</b>")
            lines.append("\n✅ Підтверджено")
            text, markup = "\n".join(lines), None
        logger.info("Wallet receipt applied: tx_id=%s parts=%s", data["w_tx_id"], [p.id for p in parts])
    await _edit_host(callback.bot, chat_id, state, text, markup)
    await state.clear()
    await callback.answer("Готово")


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
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="wna:cancel"))
    await callback.message.edit_text(
        "➕ <b>Новий рахунок</b>\n\nНапиши назву рахунку" + (" або обери назву картки:" if card else ":"),
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
    b.row(InlineKeyboardButton(text="⏭ Пропустити (0)", callback_data="wna:skip"))
    b.row(InlineKeyboardButton(text="❌ Скасувати", callback_data="wna:cancel"))
    await _edit_host(
        bot, chat_id, state,
        f"➕ Рахунок «{html.escape(name)}» ({data['w_currency']})\n\n"
        f"Введи поточний баланс рахунку — витрату буде списано з нього:",
        b.as_markup(),
    )


@router.message(WalletNewAccount.waiting_name)
async def wallet_new_account_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("Назва не може бути порожньою. Спробуй ще раз:")
        return
    await _ask_balance(message.bot, message.chat.id, state, name)


@router.message(WalletNewAccount.waiting_balance)
async def wallet_new_account_balance(message: Message, db_user: User, state: FSMContext) -> None:
    raw = (message.text or "").replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        balance = float(raw)
    except ValueError:
        await message.answer("Введи число, наприклад <i>1500</i> або <i>1500,50</i>:")
        return
    await _finish_new_account(message.bot, message.chat.id, db_user, state, balance)


@router.callback_query(F.data.startswith("wna:"))
async def wallet_new_account_buttons(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await callback.answer()
        return
    data = await state.get_data()
    if "w_target" not in data:
        await callback.answer("Діалог застарів", show_alert=True)
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
    await _edit_host(bot, chat_id, state, "Витрату вже оброблено.")


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
            text, markup = f"✅ Рахунок «{html.escape(acc.name)}» створено.", None
    await _edit_host(bot, chat_id, state, text, markup)
    await state.clear()


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
        return ("💳 Привʼязок карток Apple Wallet ще немає.\n"
                "Вони зʼявляться, коли ти обереш рахунок для нової картки."), None
    lines = ["💳 <b>Привʼязки карток Apple Wallet:</b>\n"]
    b = InlineKeyboardBuilder()
    for card, acc_name in rows:
        lines.append(f"• {html.escape(card.card_name)} → {html.escape(acc_name)}")
        b.row(InlineKeyboardButton(text=f"❌ {card.card_name}"[:60], callback_data=f"wcard:del:{card.id}"))
    b.row(InlineKeyboardButton(text="🗑 Скинути всі", callback_data="wcard:all"))
    lines.append("\nПісля скидання бот знову спитає рахунок при наступній витраті з картки.")
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
    await callback.answer("Привʼязку скинуто")
