"""Підтвердження витрат з Wallet у боті: повідомлення, кнопки, привʼязки карток."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi.testclient import TestClient
from sqlalchemy import select, func

import bot.main as bot_main
from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models import User, Account, Category, Budget, Transaction, MerchantCategory, WalletCard, WalletPending
from app.services import transaction_service, wallet_notify
from app.services.wallet_service import clean_card
from bot.handlers import wallet as wh
from conftest import wipe_db

SECRET = "test-secret"
OWNER = 777000111
STRANGER = 999


# ── Фейковий Telegram ─────────────────────────────────────────────────────────

class FakeBot:
    def __init__(self):
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self.fail = False

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        if self.fail:
            raise RuntimeError("Telegram is down")
        self.sent.append({"chat_id": chat_id, "text": text, "markup": reply_markup})
        return SimpleNamespace(message_id=100 + len(self.sent))

    async def edit_message_text(self, text, chat_id=None, message_id=None, reply_markup=None, **kw):
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "text": text, "markup": reply_markup})


class FakeMessage:
    def __init__(self, bot, text=None, user_id=OWNER, message_id=101):
        self.bot, self.text, self.message_id = bot, text, message_id
        self.chat = SimpleNamespace(id=user_id)
        self.from_user = SimpleNamespace(id=user_id)
        self.edits: list[dict] = []
        self.answers: list[str] = []

    async def edit_text(self, text, reply_markup=None, **kw):
        self.edits.append({"text": text, "markup": reply_markup})

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append(text)


class FakeCallback:
    def __init__(self, bot, data, user_id=OWNER, message=None):
        self.bot, self.data = bot, data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = message or FakeMessage(bot, user_id=user_id)
        self.answered: list = []

    async def answer(self, text=None, **kw):
        self.answered.append(text)


def buttons(markup) -> list[tuple[str, str]]:
    if markup is None:
        return []
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


# ── Фікстури ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_bot(monkeypatch):
    fb = FakeBot()
    monkeypatch.setattr(bot_main, "bot", fb)
    return fb


@pytest.fixture
def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=OWNER, user_id=OWNER))


MONTH = datetime.utcnow().strftime("%Y-%m")


@pytest.fixture(autouse=True)
def setup(client, monkeypatch):
    monkeypatch.setattr(settings, "WALLET_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "WALLET_OWNER_TG_ID", str(OWNER))
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123:fake")

    async def fake_to_uah(amount, currency):
        return amount if currency == "UAH" else amount * 40

    monkeypatch.setattr(transaction_service.exchange_rate_service, "to_uah", fake_to_uah)


def seed(client, accounts=(("Monobank", True, ["monobank"]), ("Готівка", False, []))):
    async def _seed():
        await wipe_db()
        async with AsyncSessionLocal() as db:
            user = User(telegram_id=OWNER, first_name="Owner")
            db.add(user)
            await db.flush()
            for name, is_default, kw in accounts:
                db.add(Account(user_id=user.id, name=name, currency="UAH", balance=1000.0,
                               is_default=is_default, keywords=kw))
            food = Category(user_id=user.id, name="Їжа", type="expense", icon="🍔")
            other = Category(user_id=user.id, name="Інше", type="expense", icon="💸")
            db.add_all([food, other, Category(user_id=user.id, name="Інше", type="income")])
            await db.flush()
            db.add_all([
                Budget(user_id=user.id, category_id=food.id, month=MONTH, limit_amount=5000, spent_amount=0),
                Budget(user_id=user.id, category_id=other.id, month=MONTH, limit_amount=5000, spent_amount=0),
            ])
            await db.commit()
            return user.id
    return client.portal.call(_seed)


def post(client, body, token=SECRET):
    r = client.post("/api/wallet-tx", json=body, headers={"X-Token": token})
    client.portal.call(wallet_notify.drain)
    return r


def q(client, fn):
    async def _run():
        async with AsyncSessionLocal() as db:
            return await fn(db)
    return client.portal.call(_run)


async def _user(db):
    return (await db.execute(select(User).where(User.telegram_id == OWNER))).scalar_one()


async def _accounts(db):
    return {a.name: a for a in (await db.execute(select(Account).order_by(Account.id))).scalars()}


async def _budgets(db):
    rows = (await db.execute(select(Budget, Category.name).join(Category))).all()
    return {name: b.spent_amount for b, name in rows}


def press(client, fake_bot, data, user_id=OWNER, state=None, message=None):
    cb = FakeCallback(fake_bot, data, user_id=user_id, message=message)
    db_user = q(client, _user)
    st = state or FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=user_id, user_id=user_id))
    if data.startswith("wtx:"):
        client.portal.call(wh.wallet_tx_action, cb, db_user, st)
    elif data.startswith("wpend:"):
        client.portal.call(wh.wallet_pending_new_account, cb, db_user, st)
    elif data.startswith("wna:"):
        client.portal.call(wh.wallet_new_account_buttons, cb, db_user, st)
    elif data.startswith("wcard:"):
        client.portal.call(wh.wallet_cards_reset, cb, db_user)
    return cb


YID = {"amount": "112,60 ₴", "merchant": "Yidalnia", "card": "monobankYidalniaYidalnia"}


# ── Очистка card ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("card, merchant, expected", [
    ("monobankYidalniaYidalnia", "Yidalnia", "monobank"),
    ("  VST Bank АТБ ", "АТБ", "VST Bank"),
    ("monobankyidalnia", "Yidalnia", "monobank"),          # регістр не важливий
    ("Yidalnia", "Yidalnia", None),                        # лишився порожній рядок
    ("monobank", None, "monobank"),
    (None, "АТБ", None),
])
def test_clean_card(card, merchant, expected):
    assert clean_card(card, merchant) == expected


def test_webhook_stores_cleaned_card_and_logs_raw(client, fake_bot, caplog):
    seed(client)
    caplog.set_level("INFO", logger="app.routers.wallet_webhook")
    tx_id = post(client, YID).json()["id"]
    tx = q(client, lambda db: db.get(Transaction, tx_id))
    assert tx.card == "monobank"
    assert "monobankYidalniaYidalnia" in caplog.text


# ── Повідомлення після збереження ─────────────────────────────────────────────

def test_message_sent_after_save(client, fake_bot):
    seed(client)
    q(client, _bind_monobank)
    r = post(client, YID)
    assert r.status_code == 200 and r.json()["ok"] is True
    tx = q(client, lambda db: db.get(Transaction, r.json()["id"]))
    assert tx.status == "pending"

    (msg,) = fake_bot.sent
    assert msg["chat_id"] == OWNER
    assert "112,60 ₴" in msg["text"] and "Yidalnia" in msg["text"]
    assert "Категорія: Інше" in msg["text"] and "Рахунок: Monobank" in msg["text"]
    assert "не привʼязана" not in msg["text"]            # картку вже привʼязано
    assert buttons(msg["markup"]) == [
        ("✅ Вірно", f"wtx:ok:{tx.id}"), ("📂 Категорія", f"wtx:cat:{tx.id}"), ("🗑 Видалити", f"wtx:del:{tx.id}"),
    ]


async def _bind_monobank(db):
    user, accs = await _user(db), await _accounts(db)
    db.add(WalletCard(user_id=user.id, card_name="monobank", card_key="monobank", account_id=accs["Monobank"].id))
    await db.commit()


def test_no_message_for_duplicate(client, fake_bot):
    seed(client)
    first = post(client, YID).json()["id"]
    second = post(client, YID).json()["id"]
    assert first == second
    assert len(fake_bot.sent) == 1
    assert q(client, lambda db: _count(db, Transaction)) == 1


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


def test_telegram_failure_does_not_break_webhook(client, fake_bot, caplog):
    seed(client)
    fake_bot.fail = True
    caplog.set_level("ERROR", logger="app.services.wallet_notify")
    r = post(client, YID)
    assert r.status_code == 200 and r.json()["ok"] is True
    assert q(client, lambda db: _count(db, Transaction)) == 1
    assert "Wallet notify failed" in caplog.text and "Telegram is down" in caplog.text


# ── Кнопки ────────────────────────────────────────────────────────────────────

def test_confirm_button(client, fake_bot):
    seed(client)
    q(client, _bind_monobank)
    tx_id = post(client, YID).json()["id"]
    cb = press(client, fake_bot, f"wtx:ok:{tx_id}")
    assert q(client, lambda db: db.get(Transaction, tx_id)).status == "confirmed"
    (edit,) = cb.message.edits
    assert "✅ Підтверджено" in edit["text"]
    assert buttons(edit["markup"]) == []


def test_category_button_recalculates_budgets_and_is_remembered(client, fake_bot):
    seed(client)
    q(client, _bind_monobank)
    tx_id = post(client, YID).json()["id"]
    assert q(client, _budgets) == {"Їжа": 0, "Інше": 112.6}

    cb = press(client, fake_bot, f"wtx:cat:{tx_id}")
    cat_buttons = buttons(cb.message.edits[0]["markup"])
    food_id = q(client, lambda db: _cat_id(db, "Їжа"))
    assert (f"🍔 Їжа", f"wtx:sc:{tx_id}:{food_id}") in cat_buttons

    cb = press(client, fake_bot, f"wtx:sc:{tx_id}:{food_id}")
    assert q(client, lambda db: db.get(Transaction, tx_id)).category_id == food_id
    assert q(client, _budgets) == {"Їжа": 112.6, "Інше": 0}
    assert "Категорія: Їжа" in cb.message.edits[0]["text"]
    assert q(client, lambda db: _count(db, MerchantCategory)) == 1

    # Наступна витрата у того ж продавця — одразу в «Їжа» (раніше ніж словник/«Інше»)
    tx2 = post(client, {**YID, "amount": "50 ₴"}).json()["id"]
    assert q(client, lambda db: db.get(Transaction, tx2)).category_id == food_id
    assert "Категорія: Їжа" in fake_bot.sent[-1]["text"]


async def _cat_id(db, name):
    return (await db.execute(select(Category.id).where(Category.name == name, Category.type == "expense"))).scalar_one()


def test_delete_button_restores_balance_and_budget(client, fake_bot):
    seed(client)
    q(client, _bind_monobank)
    tx_id = post(client, YID).json()["id"]
    assert q(client, _accounts)["Monobank"].balance == pytest.approx(1000 - 112.6)
    assert q(client, _budgets)["Інше"] == pytest.approx(112.6)

    cb = press(client, fake_bot, f"wtx:del:{tx_id}")
    assert q(client, lambda db: db.get(Transaction, tx_id)) is None
    assert q(client, _accounts)["Monobank"].balance == pytest.approx(1000.0)
    assert q(client, _budgets)["Інше"] == pytest.approx(0.0)
    assert "Видалено" in cb.message.edits[0]["text"] and cb.message.edits[0]["markup"] is None


def test_foreign_callbacks_are_ignored(client, fake_bot):
    seed(client)
    tx_id = post(client, YID).json()["id"]
    for data in (f"wtx:ok:{tx_id}", f"wtx:del:{tx_id}", f"wtx:new:{tx_id}"):
        cb = press(client, fake_bot, data, user_id=STRANGER)
        assert cb.message.edits == []
    tx = q(client, lambda db: db.get(Transaction, tx_id))
    assert tx is not None and tx.status == "pending"


# ── Привʼязка карток ──────────────────────────────────────────────────────────

def test_first_spend_with_new_card_asks_for_account(client, fake_bot):
    seed(client)
    tx_id = post(client, {"amount": "10 ₴", "merchant": "АТБ", "card": "VST BankАТБ"}).json()["id"]
    tx = q(client, lambda db: db.get(Transaction, tx_id))
    accs = q(client, _accounts)
    assert tx.card == "VST Bank" and tx.account_id == accs["Monobank"].id   # рахунок за замовчуванням

    (msg,) = fake_bot.sent
    assert "Картка «VST Bank» ще не привʼязана до рахунку" in msg["text"]
    btns = buttons(msg["markup"])
    assert btns[3:] == [
        ("⭐ Monobank (підказка)", f"wtx:bind:{tx_id}:{accs['Monobank'].id}"),
        ("Готівка", f"wtx:bind:{tx_id}:{accs['Готівка'].id}"),
        ("➕ Новий рахунок", f"wtx:new:{tx_id}"),
    ]


def test_keyword_suggestion_goes_first(client, fake_bot):
    seed(client, accounts=(("Готівка", True, []), ("Monobank", False, ["monobank"])))
    tx_id = post(client, YID).json()["id"]
    accs = q(client, _accounts)
    assert q(client, lambda db: db.get(Transaction, tx_id)).account_id == accs["Monobank"].id
    assert buttons(fake_bot.sent[0]["markup"])[3][0] == "⭐ Monobank (підказка)"


def test_bind_to_existing_account_moves_balance(client, fake_bot):
    seed(client)
    tx_id = post(client, {"amount": "100 ₴", "merchant": "АТБ", "card": "VST Bank"}).json()["id"]
    accs = q(client, _accounts)
    assert accs["Monobank"].balance == 900 and accs["Готівка"].balance == 1000

    cb = press(client, fake_bot, f"wtx:bind:{tx_id}:{accs['Готівка'].id}")
    accs = q(client, _accounts)
    assert accs["Monobank"].balance == 1000 and accs["Готівка"].balance == 900
    assert q(client, lambda db: db.get(Transaction, tx_id)).account_id == accs["Готівка"].id
    edit = cb.message.edits[0]
    assert "Рахунок: Готівка" in edit["text"] and "не привʼязана" not in edit["text"]

    # Наступні витрати з картки — одразу на привʼязаний рахунок, без питань
    tx2 = post(client, {"amount": "5 ₴", "merchant": "Кафе", "card": "VST Bank"}).json()["id"]
    assert q(client, lambda db: db.get(Transaction, tx2)).account_id == accs["Готівка"].id
    assert "не привʼязана" not in fake_bot.sent[-1]["text"]


def test_new_account_dialog(client, fake_bot, state):
    seed(client)
    tx_id = post(client, {"amount": "12,99 €", "merchant": "Shop", "card": "Revolut"}).json()["id"]
    host = FakeMessage(fake_bot, message_id=555)

    cb = press(client, fake_bot, f"wtx:new:{tx_id}", state=state, message=host)
    assert ("✏️ Revolut", "wna:usecard") in buttons(host.edits[-1]["markup"])

    press(client, fake_bot, "wna:usecard", state=state, message=host)
    assert "Введи поточний баланс" in fake_bot.edited[-1]["text"]
    assert ("⏭ Пропустити (0)", "wna:skip") in buttons(fake_bot.edited[-1]["markup"])

    db_user = q(client, _user)
    client.portal.call(wh.wallet_new_account_balance, FakeMessage(fake_bot, text="500"), db_user, state)

    accs = q(client, _accounts)
    assert accs["Monobank"].balance == pytest.approx(1000.0)            # повернули на старий
    rev = accs["Revolut"]
    assert rev.currency == "EUR" and rev.balance == pytest.approx(500 - 12.99)
    assert q(client, lambda db: db.get(Transaction, tx_id)).account_id == rev.id
    binding = q(client, lambda db: _first(db, WalletCard))
    assert binding.card_name == "Revolut" and binding.account_id == rev.id
    final = fake_bot.edited[-1]
    assert final["message_id"] == 555 and "Рахунок: Revolut" in final["text"]
    assert client.portal.call(state.get_state) is None


async def _first(db, model):
    return (await db.execute(select(model))).scalars().first()


def test_no_accounts_saves_pending_and_creates_account(client, fake_bot, state):
    seed(client, accounts=())
    r = post(client, YID)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and "id" not in body and body["pending_id"]
    assert q(client, lambda db: _count(db, Transaction)) == 0
    (msg,) = fake_bot.sent
    assert "немає рахунків" in msg["text"]
    assert buttons(msg["markup"]) == [("➕ Новий рахунок", f"wpend:new:{body['pending_id']}")]

    # Повтор у межах 60 с — без другого запису й повідомлення
    assert post(client, YID).json() == {"ok": True, "pending_id": body["pending_id"]}
    assert len(fake_bot.sent) == 1

    host = FakeMessage(fake_bot, message_id=777)
    press(client, fake_bot, f"wpend:new:{body['pending_id']}", state=state, message=host)
    db_user = q(client, _user)
    client.portal.call(wh.wallet_new_account_name, FakeMessage(fake_bot, text="Моно"), state)
    press(client, fake_bot, "wna:skip", state=state, message=host)

    accs = q(client, _accounts)
    assert list(accs) == ["Моно"]
    acc = accs["Моно"]
    assert acc.is_default and acc.balance == pytest.approx(-112.6)
    tx = q(client, lambda db: _first(db, Transaction))
    assert tx.amount == 112.6 and tx.account_id == acc.id and tx.card == "monobank" and tx.status == "pending"
    assert q(client, lambda db: _count(db, WalletPending)) == 0
    assert q(client, lambda db: _first(db, WalletCard)).account_id == acc.id
    assert "Рахунок: Моно" in fake_bot.edited[-1]["text"]


# ── /cards ────────────────────────────────────────────────────────────────────

def test_cards_command_lists_and_resets(client, fake_bot):
    seed(client)
    q(client, _bind_monobank)
    db_user = q(client, _user)
    msg = FakeMessage(fake_bot)
    client.portal.call(wh.cmd_cards, msg, db_user)
    assert "monobank → Monobank" in msg.answers[0]

    binding = q(client, lambda db: _first(db, WalletCard))
    cb = press(client, fake_bot, f"wcard:del:{binding.id}")
    assert q(client, lambda db: _count(db, WalletCard)) == 0
    assert "ще немає" in cb.message.edits[0]["text"]

    # Після скидання бот знову питає рахунок
    post(client, YID)
    assert "не привʼязана" in fake_bot.sent[-1]["text"]


def test_fmt_amount():
    assert wh.fmt_amount(112.6, "UAH") == "112,60 ₴"
    assert wh.fmt_amount(1250.5, "UAH") == "1 250,50 ₴"
    assert wh.fmt_amount(5, "USD") == "5,00 $"


def test_webhook_does_not_wait_for_telegram(client, fake_bot):
    """Відповідь вебхука не чекає Telegram: «зависле» надсилання завершується вже після неї."""
    import asyncio
    seed(client)
    release = client.portal.call(asyncio.Event)
    original_send = fake_bot.send_message

    async def slow_send(*args, **kwargs):
        await release.wait()
        return await original_send(*args, **kwargs)

    fake_bot.send_message = slow_send
    r = client.post("/api/wallet-tx", json=YID, headers={"X-Token": SECRET})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert fake_bot.sent == []                    # відповідь уже є, повідомлення ще ні
    client.portal.call(release.set)
    client.portal.call(wallet_notify.drain)
    assert len(fake_bot.sent) == 1


# ── Наскрізно через aiogram Dispatcher (middleware + фільтри + порядок роутерів) ──

def test_dispatcher_routes_wallet_updates(client, fake_bot):
    from aiogram import Bot
    from aiogram.client.session.base import BaseSession
    from aiogram.methods import EditMessageText
    from aiogram.types import Update

    calls = []

    class RecordingSession(BaseSession):
        async def make_request(self, bot, method, timeout=None):
            calls.append(method)
            return True

        async def stream_content(self, *a, **kw):
            yield b""

        async def close(self):
            pass

    seed(client)
    q(client, _bind_monobank)
    tx_id = post(client, YID).json()["id"]
    tg_bot = Bot("123:fake", session=RecordingSession())
    user = {"id": OWNER, "is_bot": False, "first_name": "Owner"}
    chat = {"id": OWNER, "type": "private"}

    def feed(update: dict):
        client.portal.call(bot_main.dp.feed_update, tg_bot, Update.model_validate(update))

    feed({"update_id": 1, "callback_query": {
        "id": "1", "from": user, "chat_instance": "x", "data": f"wtx:ok:{tx_id}",
        "message": {"message_id": 10, "date": 0, "chat": chat, "text": "💳"}}})
    assert q(client, lambda db: db.get(Transaction, tx_id)).status == "confirmed"
    assert any(isinstance(m, EditMessageText) and "Підтверджено" in m.text for m in calls)

    calls.clear()
    feed({"update_id": 2, "message": {"message_id": 11, "date": 0, "chat": chat, "from": user, "text": "/cards"}})
    assert any("monobank → Monobank" in getattr(m, "text", "") for m in calls)
