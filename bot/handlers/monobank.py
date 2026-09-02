"""Інтеграція з Monobank Open API.

Бот-флоу підключення:
  Інструкція → токен → валідація client-info → мультиселект карток →
  автостворення рахунків → вибір періоду бекфілу → тихий імпорт →
  реєстрація webhook.

Вхідні webhook-події обробляє handle_webhook_statement() — вона будує
повідомлення-підтвердження з inline-кнопками, яке цей роутер і опрацьовує.

Токен зберігається лише у зашифрованому вигляді (bank_connections) і
ніколи не логується.
"""
import logging
import time
from itertools import count

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal
from app.models import User, Account, Category, Transaction, BankConnection, BankCard
from app.services.exchange_rate_service import exchange_rate_service
from app.services.monobank_service import (
    monobank_service, currency_alpha, mcc_to_hint, parse_statement_item,
)
from app.services import token_crypto
from app.config import settings

from bot.keyboards.inline import (
    monobank_menu_keyboard, monobank_connection_keyboard,
    mono_cards_keyboard, mono_backfill_keyboard,
    mono_confirm_keyboard, mono_category_keyboard,
    back_keyboard,
)
from bot.services.category_matcher import match_category
from bot.states import ConnectMonobank, MonoComment
from bot.utils.fsm_edit import edit_host, HOST_MID_KEY
from bot.utils.tx_helpers import save_transaction

logger = logging.getLogger(__name__)
router = Router()

# ── Черга підтверджень (in-memory, як і FSM MemoryStorage застосунку) ─────────
# pid → dict з даними операції, що очікує підтвердження користувача.
_pending: dict[str, dict] = {}
_pid_counter = count(1)
_MAX_PENDING = 1000


def _register_pending(data: dict) -> str:
    pid = str(next(_pid_counter))
    _pending[pid] = data
    if len(_pending) > _MAX_PENDING:
        # прибираємо найстаріші
        for old in list(_pending.keys())[: len(_pending) - _MAX_PENDING]:
            _pending.pop(old, None)
    return pid


def clear_pending_for_user(user_id: int) -> int:
    """Прибирає непідтверджені Monobank-операції юзера (напр. після reset даних),
    щоб не лишалось застарілих confirm-кнопок на видалені дані."""
    stale = [pid for pid, p in _pending.items() if p.get("user_id") == user_id]
    for pid in stale:
        _pending.pop(pid, None)
    return len(stale)


# ── Утиліти ───────────────────────────────────────────────────────────────────

def _last4(*candidates: str | None) -> str:
    for c in candidates:
        if c:
            digits = "".join(ch for ch in c if ch.isdigit())
            if len(digits) >= 4:
                return digits[-4:]
    return "????"


def _accounts_from_client_info(client_info: dict) -> list[dict]:
    """client-info → список карток для мультиселекту/створення рахунків."""
    result = []
    for acc in client_info.get("accounts", []):
        masked = (acc.get("maskedPan") or [None])[0]
        result.append({
            "id": acc.get("id"),
            "currency_code": acc.get("currencyCode", 980),
            "currency": currency_alpha(acc.get("currencyCode", 980)),
            "masked_pan": masked,
            "last4": _last4(masked, acc.get("iban"), acc.get("id")),
            "balance": (acc.get("balance") or 0) / 100,
        })
    return result


# ── Меню Monobank у налаштуваннях ─────────────────────────────────────────────

@router.callback_query(F.data == "mono:menu")
async def mono_menu(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await state.clear()
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(BankConnection)
            .where(BankConnection.user_id == db_user.id)
            .options(selectinload(BankConnection.cards))
        )
        connections = res.scalars().all()

    text = (
        "🏦 <b>Monobank</b>\n\n"
        + ("Ваші підключення:" if connections else "Підключень ще немає.\n"
           "Підключіть Monobank, щоб автоматично отримувати операції.")
    )
    await callback.message.edit_text(text, reply_markup=monobank_menu_keyboard(connections))
    await callback.answer()


@router.callback_query(F.data.startswith("mono:view:"))
async def mono_view_connection(callback: CallbackQuery, db_user: User) -> None:
    conn_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(BankConnection)
            .where(and_(BankConnection.id == conn_id, BankConnection.user_id == db_user.id))
            .options(selectinload(BankConnection.cards))
        )
        conn = res.scalar_one_or_none()
    if not conn:
        await callback.answer("Підключення не знайдено")
        return
    lines = ["💳 <b>Monobank</b>\n", f"Відстежуються карток: {sum(c.is_tracked for c in conn.cards)}"]
    await callback.message.edit_text("\n".join(lines), reply_markup=monobank_connection_keyboard(conn_id))
    await callback.answer()


@router.callback_query(F.data.startswith("mono:disconnect_confirm:"))
async def mono_disconnect(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    """Відключення: видаляє з'єднання та картки; рахунки/транзакції лишаються."""
    conn_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(BankConnection).where(
                and_(BankConnection.id == conn_id, BankConnection.user_id == db_user.id)
            )
        )
        conn = res.scalar_one_or_none()
        if conn:
            await db.delete(conn)  # cascade прибирає bank_cards, рахунки лишаються
            await db.commit()
    await callback.answer("✅ Monobank відключено", show_alert=True)
    await mono_menu(callback, db_user, state)


# ── Крок 1: інструкція + очікування токена ────────────────────────────────────

@router.callback_query(F.data == "mono:start")
async def mono_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not token_crypto.is_configured():
        await callback.answer("Інтеграцію не налаштовано (TOKEN_ENCRYPTION_KEY)", show_alert=True)
        return
    await state.clear()
    await state.set_state(ConnectMonobank.waiting_token)
    await state.update_data(**{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text(
        "🏦 <b>Підключення Monobank</b>\n\n"
        "1. Відкрийте <a href=\"https://api.monobank.ua/\">api.monobank.ua</a>\n"
        "2. Увійдіть через застосунок Monobank\n"
        "3. Створіть та скопіюйте <b>особистий токен</b>\n"
        "4. Надішліть його наступним повідомленням\n\n"
        "🔒 Токен зберігається у зашифрованому вигляді й ніколи не показується.",
        reply_markup=back_keyboard("mono:menu"),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.message(ConnectMonobank.waiting_token)
async def mono_receive_token(message: Message, state: FSMContext) -> None:
    token = (message.text or "").strip()
    # Прибираємо повідомлення з токеном, щоб він не лишався в чаті
    try:
        await message.delete()
    except Exception:
        pass

    if not token or len(token) < 20:
        await edit_host(message, state, "❌ Схоже, це некоректний токен. Спробуйте ще раз:",
                        reply_markup=back_keyboard("mono:menu"))
        return

    await edit_host(message, state, "⏳ Перевіряю токен...")
    try:
        client_info = await monobank_service.get_client_info(token)
    except Exception as e:
        logger.warning("Monobank client-info failed: %s", e.__class__.__name__)
        await edit_host(message, state,
                        "❌ Не вдалось підключитись. Перевірте токен і спробуйте ще раз:",
                        reply_markup=back_keyboard("mono:menu"))
        return

    accounts = _accounts_from_client_info(client_info)
    if not accounts:
        await edit_host(message, state, "❌ У цьому акаунті немає доступних рахунків.",
                        reply_markup=back_keyboard("mono:menu"))
        return

    await state.update_data(mono_token=token, mono_accounts=accounts, mono_selected=[])
    await state.set_state(ConnectMonobank.selecting_cards)
    name = client_info.get("name", "клієнт")
    await edit_host(
        message, state,
        f"✅ Підключено як <b>{name}</b>.\n\nОберіть картки для відстеження:",
        reply_markup=mono_cards_keyboard(accounts, set()),
    )


# ── Крок 2: мультиселект карток ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("mono:toggle:"), ConnectMonobank.selecting_cards)
async def mono_toggle_card(callback: CallbackQuery, state: FSMContext) -> None:
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    accounts = data.get("mono_accounts", [])
    selected = set(data.get("mono_selected", []))
    if idx in selected:
        selected.discard(idx)
    else:
        selected.add(idx)
    await state.update_data(mono_selected=sorted(selected))
    await callback.message.edit_reply_markup(reply_markup=mono_cards_keyboard(accounts, selected))
    await callback.answer()


@router.callback_query(F.data == "mono:cards_done", ConnectMonobank.selecting_cards)
async def mono_cards_done(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    data = await state.get_data()
    accounts = data.get("mono_accounts", [])
    selected = sorted(set(data.get("mono_selected", [])))
    token = data.get("mono_token")
    if not selected:
        await callback.answer("Оберіть хоча б одну картку", show_alert=True)
        return

    # Створюємо з'єднання (зашифрований токен), картки та дзеркальні рахунки.
    async with AsyncSessionLocal() as db:
        conn = BankConnection(
            user_id=db_user.id,
            provider="monobank",
            encrypted_token=token_crypto.encrypt_token(token),
        )
        db.add(conn)
        await db.flush()

        for idx in selected:
            acc = accounts[idx]
            name = f"Mono {acc['currency']} •{acc['last4']}"
            # Автоматичне налаштування рахунку: назва, валюта, поточний баланс
            local_acc = Account(
                user_id=db_user.id,
                name=name,
                currency=acc["currency"],
                balance=acc["balance"],
                keywords=[name.lower(), "mono", "monobank"],
            )
            db.add(local_acc)
            await db.flush()
            db.add(BankCard(
                connection_id=conn.id,
                mono_account_id=acc["id"],
                masked_pan=acc.get("masked_pan"),
                currency_code=acc["currency_code"],
                account_id=local_acc.id,
                is_tracked=True,
            ))
        await db.commit()
        conn_id = conn.id

    await state.update_data(mono_connection_id=conn_id)
    await state.set_state(ConnectMonobank.selecting_period)
    await callback.message.edit_text(
        f"✅ Додано рахунків: <b>{len(selected)}</b>.\n\n"
        "Підтягнути історію операцій?",
        reply_markup=mono_backfill_keyboard(),
    )
    await callback.answer()


# ── Крок 3: бекфіл + реєстрація webhook ───────────────────────────────────────

_PERIOD_LABELS = {"week": "тиждень", "month": "31 день", "none": ""}
_PERIOD_SECONDS = {"week": 7 * 24 * 3600, "month": 31 * 24 * 3600}


@router.callback_query(F.data.startswith("mono:bf:"), ConnectMonobank.selecting_period)
async def mono_backfill(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    period = callback.data.split(":")[2]
    data = await state.get_data()
    conn_id = data.get("mono_connection_id")
    token = data.get("mono_token")
    await state.clear()
    # Acknowledge одразу — бекфіл через ліміт 60 с може тривати довго
    await callback.answer()

    imported = 0
    total_sum = 0.0
    if period in _PERIOD_SECONDS:
        await callback.message.edit_text("⏳ Імпортую операції (це може зайняти хвилину)...")
        imported, total_sum = await _run_backfill(db_user.id, conn_id, token, period)

    # Реєстрація webhook після бекфілу (щоб уникнути подвійного обліку).
    webhook_ok = await _register_webhook(conn_id, token)

    lines = []
    if period in _PERIOD_SECONDS:
        lines.append(
            f"✅ Імпортовано {imported} операцій за {_PERIOD_LABELS[period]} "
            f"на суму {total_sum:,.2f} ₴"
        )
    else:
        lines.append("✅ Monobank підключено.")
    lines.append("🔔 Нові операції надходитимуть автоматично."
                 if webhook_ok else
                 "⚠️ Не вдалось зареєструвати webhook — нові операції не надходитимуть автоматично.")

    await callback.message.edit_text("\n".join(lines), reply_markup=back_keyboard("mono:menu"))


async def _register_webhook(conn_id: int, token: str) -> bool:
    base = (settings.WEBHOOK_BASE_URL or settings.WEBHOOK_URL).rstrip("/")
    if not base or not conn_id or not token:
        return False
    url = f"{base}/webhooks/monobank/{conn_id}"
    try:
        await monobank_service.set_webhook(token, url)
    except Exception as e:
        logger.warning("Monobank set_webhook failed: %s", e.__class__.__name__)
        return False
    async with AsyncSessionLocal() as db:
        conn = await db.get(BankConnection, conn_id)
        if conn:
            conn.webhook_url = url
            await db.commit()
    return True


def _match_local(hint: str, description: str, cats: list[Category]) -> int | None:
    """Швидка локальна категоризація (без API) — для масового імпорту."""
    hint_l = (hint or "").lower()
    desc_l = (description or "").lower()
    for c in cats:
        nl = c.name.lower()
        if hint_l and (hint_l in nl or nl in hint_l):
            return c.id
    for c in cats:
        if c.name.lower() in desc_l:
            return c.id
    return None


async def _run_backfill(user_id: int, conn_id: int, token: str, period: str) -> tuple[int, float]:
    """Тихий імпорт історії: виписка → автокатегоризація → масова вставка.

    Баланс рахунку НЕ коригується — він уже містить актуальне значення з
    client-info (історичні операції в ньому враховані). Змінюють баланс лише
    майбутні операції, що приходять через webhook.
    """
    now = int(time.time())
    from_ts = now - _PERIOD_SECONDS[period]

    async with AsyncSessionLocal() as db:
        cards_res = await db.execute(
            select(BankCard).where(and_(BankCard.connection_id == conn_id, BankCard.is_tracked == True))
        )
        cards = cards_res.scalars().all()
        cats_res = await db.execute(select(Category).where(Category.user_id == user_id))
        all_cats = cats_res.scalars().all()

    cats_by_type = {"expense": [c for c in all_cats if c.type == "expense"],
                    "income": [c for c in all_cats if c.type == "income"]}

    imported = 0
    total_uah = 0.0
    for card in cards:
        try:
            # get_statement дотримується ліміту 60 с — картки опрацьовуються послідовно
            raw_items = await monobank_service.get_statement(token, card.mono_account_id, from_ts, now)
        except Exception as e:
            logger.warning("Monobank statement failed for %s: %s", card.mono_account_id, e.__class__.__name__)
            continue

        async with AsyncSessionLocal() as db:
            for raw in raw_items:
                parsed = parse_statement_item(raw, card.currency_code)
                if parsed is None:  # hold=true
                    continue
                cat_id = _match_local(mcc_to_hint(parsed["mcc"]), parsed["description"],
                                      cats_by_type.get(parsed["tx_type"], []))
                amount_uah = await exchange_rate_service.to_uah(parsed["amount"], parsed["currency"])
                db.add(Transaction(
                    user_id=user_id,
                    account_id=card.account_id,
                    category_id=cat_id,
                    type=parsed["tx_type"],
                    amount=parsed["amount"],
                    currency=parsed["currency"],
                    amount_uah=amount_uah,
                    description=parsed["description"] or None,
                    source="monobank_import",
                    external_id=parsed["mono_id"],
                ))
                imported += 1
                total_uah += amount_uah if parsed["tx_type"] == "income" else -amount_uah
            await db.commit()

    return imported, total_uah


@router.callback_query(F.data == "mono:cancel")
async def mono_cancel(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await mono_menu(callback, db_user, state)


# ── Вхідні webhook-операції: підтвердження користувача ─────────────────────────

async def handle_webhook_statement(connection_id: int, mono_account_id: str, item: dict) -> None:
    """Точка входу webhook-роутера — делегує у спільний обробник."""
    await _process_statement_item(connection_id, mono_account_id, item)


def _has_pending_external(user_id: int, external_id: str) -> bool:
    """Чи вже є непідтверджений confirm для цієї операції (дедуп у памʼяті)."""
    return any(
        p.get("user_id") == user_id and p.get("external_id") == external_id
        for p in _pending.values()
    )


async def _process_statement_item(connection_id: int, mono_account_id: str, item: dict) -> None:
    """Обробляє один StatementItem: пошук картки → парсинг → дедуп →
    категоризація → надсилання підтвердження.

    Спільна логіка для webhook-хендлера та reconciliation-job. Ідемпотентна:
    якщо операцію вже записано (Transaction з таким external_id) або по ній вже
    висить непідтверджений confirm — тихо пропускає, не дублюючи ні транзакцію,
    ні повідомлення. Мовчки (з логом) ігнорує невідстежувані картки та hold.
    """
    async with AsyncSessionLocal() as db:
        card_res = await db.execute(
            select(BankCard).where(
                and_(BankCard.connection_id == connection_id,
                     BankCard.mono_account_id == mono_account_id)
            )
        )
        card = card_res.scalar_one_or_none()
        if not card or not card.is_tracked or not card.account_id:
            logger.info(
                "Monobank webhook ignored: card=%s tracked=%s account_id=%s "
                "(connection_id=%s, mono_account_id=%s)",
                bool(card), card.is_tracked if card else None,
                card.account_id if card else None, connection_id, mono_account_id,
            )
            return
        conn = await db.get(BankConnection, connection_id)
        user = await db.get(User, conn.user_id) if conn else None
        account = await db.get(Account, card.account_id)
        if not user or not account:
            logger.info(
                "Monobank webhook ignored: user=%s account=%s "
                "(connection_id=%s, mono_account_id=%s, account_id=%s)",
                bool(user), bool(account), connection_id, mono_account_id, card.account_id,
            )
            return

        parsed = parse_statement_item(item, card.currency_code)
        if parsed is None:  # hold
            logger.info(
                "Monobank webhook ignored: hold=true (connection_id=%s, mono_account_id=%s, item_id=%s)",
                connection_id, mono_account_id, item.get("id"),
            )
            return

        external_id = parsed.get("mono_id")
        # Дедуп: операцію вже записано (backfill / підтверджений confirm)?
        if external_id:
            already = await db.execute(
                select(Transaction.id).where(
                    and_(Transaction.user_id == user.id, Transaction.external_id == external_id)
                )
            )
            if already.first():
                logger.info(
                    "Monobank item already recorded — skip (user_id=%s, external_id=%s)",
                    user.id, external_id,
                )
                return

        tx_type = parsed["tx_type"]
        cats_res = await db.execute(
            select(Category).where(and_(Category.user_id == user.id, Category.type == tx_type))
        )
        cats = cats_res.scalars().all()

    # Дедуп: по цій операції вже висить непідтверджений confirm?
    if external_id and _has_pending_external(user.id, external_id):
        logger.info(
            "Monobank item already awaiting confirm — skip (user_id=%s, external_id=%s)",
            user.id, external_id,
        )
        return

    cats_for_matcher = [{"id": c.id, "name": c.name} for c in cats]
    cat_match = await match_category(
        description=parsed["description"],
        hint=mcc_to_hint(parsed["mcc"]),
        tx_type=tx_type,
        user_categories=cats_for_matcher,
    )
    category_id = cat_match.get("matched_id")
    category_name = cat_match.get("name") or cat_match.get("new_name") or "Без категорії"

    pid = _register_pending({
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "account_id": account.id,
        "account_name": account.name,
        "tx_type": tx_type,
        "amount": parsed["amount"],
        "currency": parsed["currency"],
        "description": parsed["description"],
        "category_id": category_id,
        "category_name": category_name,
        "external_id": external_id,
    })

    from bot.main import bot
    try:
        await bot.send_message(user.telegram_id, _confirm_text(_pending[pid]),
                               reply_markup=mono_confirm_keyboard(pid))
    except Exception as e:
        logger.warning("Monobank confirm send failed: %s", e.__class__.__name__)
        _pending.pop(pid, None)


def _combined_description(p: dict) -> str | None:
    """Опис операції з коментарем користувача (якщо є): '{опис} — {коментар}'."""
    orig = p.get("description")
    comment = p.get("custom_comment")
    if comment:
        return f"{orig} — {comment}" if orig else comment
    return orig


def _confirm_text(p: dict) -> str:
    emoji = "➕" if p["tx_type"] == "income" else "➖"
    return (
        f"🏦 <b>Нова операція Monobank</b>\n\n"
        f"{emoji} <b>{p['amount']:.2f} {p['currency']}</b>\n"
        f"📝 {_combined_description(p) or '—'}\n"
        f"🏦 {p.get('account_name', '—')}\n"
        f"🏷 {p.get('category_name', 'Без категорії')}\n\n"
        f"Додати цю операцію?"
    )


def _pending_to_tx(p: dict) -> dict:
    return {
        "parsed": {},
        "tx_type": p["tx_type"],
        "amount": p["amount"],
        "currency": p["currency"],
        "description": _combined_description(p),
        "account_id": p["account_id"],
        "category_id": p.get("category_id"),
        "source": "monobank",
        "external_id": p.get("external_id"),
    }


@router.callback_query(F.data.startswith("mono:ok:"))
async def mono_confirm_ok(callback: CallbackQuery, db_user: User) -> None:
    pid = callback.data.split(":")[2]
    p = _pending.get(pid)
    if not p or p.get("user_id") != db_user.id:
        await callback.answer("Операція застаріла", show_alert=True)
        return
    _pending.pop(pid, None)
    tx = await save_transaction(db_user.id, _pending_to_tx(p))
    await callback.message.edit_text(
        f"✅ <b>Додано операцію Monobank</b>\n\n"
        f"💵 {tx.amount:.2f} {tx.currency}\n"
        f"📝 {tx.description or '—'}\n"
        f"🏷 {p.get('category_name', 'Без категорії')}",
        reply_markup=back_keyboard("menu:main"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mono:skip:"))
async def mono_confirm_skip(callback: CallbackQuery, db_user: User) -> None:
    pid = callback.data.split(":")[2]
    _pending.pop(pid, None)
    await callback.message.edit_text("🚫 Операцію не враховано.", reply_markup=back_keyboard("menu:main"))
    await callback.answer()


@router.callback_query(F.data.startswith("mono:edit:"))
async def mono_confirm_edit(callback: CallbackQuery, db_user: User) -> None:
    pid = callback.data.split(":")[2]
    p = _pending.get(pid)
    if not p or p.get("user_id") != db_user.id:
        await callback.answer("Операція застаріла", show_alert=True)
        return
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category).where(
                and_(Category.user_id == db_user.id, Category.type == p["tx_type"])
            )
        )
        cats = res.scalars().all()
    await callback.message.edit_text(
        "🏷 Оберіть категорію для операції:",
        reply_markup=mono_category_keyboard(cats, pid),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mono:cat:"))
async def mono_confirm_set_category(callback: CallbackQuery, db_user: User) -> None:
    _, _, pid, cat_id = callback.data.split(":")
    p = _pending.get(pid)
    if not p or p.get("user_id") != db_user.id:
        await callback.answer("Операція застаріла", show_alert=True)
        return
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Category).where(and_(Category.id == int(cat_id), Category.user_id == db_user.id))
        )
        cat = res.scalar_one_or_none()
    if not cat:
        await callback.answer("Категорію не знайдено")
        return
    p["category_id"] = cat.id
    p["category_name"] = cat.name
    _pending.pop(pid, None)
    tx = await save_transaction(db_user.id, _pending_to_tx(p))
    await callback.message.edit_text(
        f"✅ <b>Додано операцію Monobank</b>\n\n"
        f"💵 {tx.amount:.2f} {tx.currency}\n"
        f"📝 {tx.description or '—'}\n"
        f"🏷 {cat.name}",
        reply_markup=back_keyboard("menu:main"),
    )
    await callback.answer()


# ── Коментар до операції ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mono:comment:"))
async def mono_comment_start(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    pid = callback.data.split(":")[2]
    p = _pending.get(pid)
    if not p or p.get("user_id") != db_user.id:
        await callback.answer("Операція застаріла", show_alert=True)
        return
    await state.set_state(MonoComment.waiting_text)
    await state.update_data(mono_pid=pid, **{HOST_MID_KEY: callback.message.message_id})
    await callback.message.edit_text("💬 Напиши коментар до цієї операції:")
    await callback.answer()


@router.message(MonoComment.waiting_text)
async def mono_comment_input(message: Message, db_user: User, state: FSMContext) -> None:
    comment = (message.text or "").strip()
    data = await state.get_data()
    pid = data.get("mono_pid")
    try:
        await message.delete()  # прибираємо повідомлення юзера, лишаємо єдину картку
    except Exception:
        pass

    p = _pending.get(pid)
    if not p or p.get("user_id") != db_user.id:
        await edit_host(message, state, "Операція застаріла.", reply_markup=back_keyboard("menu:main"))
        await state.clear()
        return

    if comment:
        p["custom_comment"] = comment[:200]
    # Повертаємо ту саму картку підтвердження (тепер з коментарем в описі)
    await edit_host(message, state, _confirm_text(p), reply_markup=mono_confirm_keyboard(pid))
    await state.clear()
