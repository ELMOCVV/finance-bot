"""«🧹 Почати з нуля»: скидання історії та стартові баланси."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.main import app
from app.models import (
    User, Account, Category, Budget, Goal, Debt, Transaction, Transfer, WalletPending, MerchantCategory,
)
from bot.handlers import monobank as mono
from bot.handlers import reset as rh
from conftest import wipe_db

TG = 555000111
MONTH = datetime.utcnow().strftime("%Y-%m")


class FakeBot:
    def __init__(self):
        self.edited, self.sent = [], []

    async def edit_message_text(self, text, chat_id=None, message_id=None, reply_markup=None, **kw):
        self.edited.append({"message_id": message_id, "text": text, "markup": reply_markup})

    async def send_message(self, chat_id, text, reply_markup=None, **kw):
        self.sent.append({"text": text, "markup": reply_markup})


class FakeMessage:
    def __init__(self, bot, text=None, message_id=50):
        self.bot, self.text, self.message_id = bot, text, message_id
        self.chat = SimpleNamespace(id=TG)
        self.edits, self.answers = [], []

    async def edit_text(self, text, reply_markup=None, **kw):
        self.edits.append({"text": text, "markup": reply_markup})

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append(text)


class FakeCallback:
    def __init__(self, bot, data, message):
        self.bot, self.data, self.message = bot, data, message
        self.from_user = SimpleNamespace(id=TG)

    async def answer(self, *a, **kw):
        pass


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=TG, user_id=TG))


def q(client, fn):
    async def _run():
        async with AsyncSessionLocal() as db:
            return await fn(db)
    return client.portal.call(_run)


def seed(client):
    async def _seed():
        await wipe_db()
        async with AsyncSessionLocal() as db:
            user = User(telegram_id=TG, first_name="Me")
            other = User(telegram_id=TG + 1, first_name="Other")
            db.add_all([user, other])
            await db.flush()
            mono_acc = Account(user_id=user.id, name="Monobank", currency="UAH", balance=-3200.0, is_default=True, keywords=[])
            usd = Account(user_id=user.id, name="Долари", currency="USD", balance=50.0, is_default=False, keywords=[])
            other_acc = Account(user_id=other.id, name="Чужий", currency="UAH", balance=999.0, is_default=True, keywords=[])
            db.add_all([mono_acc, usd, other_acc])
            food = Category(user_id=user.id, name="Їжа", type="expense")
            db.add(food)
            await db.flush()
            db.add_all([
                Transaction(user_id=user.id, account_id=mono_acc.id, category_id=food.id, type="expense",
                            amount=100, amount_uah=100),
                Transaction(user_id=user.id, account_id=mono_acc.id, type="income", amount=5000, amount_uah=5000),
                Transaction(user_id=other.id, account_id=other_acc.id, type="expense", amount=1, amount_uah=1),
                Transfer(user_id=user.id, from_account_id=mono_acc.id, to_account_id=usd.id, amount=10, amount_uah=10),
                WalletPending(user_id=user.id, amount=5, currency="UAH", merchant="АТБ"),
                Budget(user_id=user.id, category_id=food.id, month=MONTH, limit_amount=3000, spent_amount=100),
                Goal(user_id=user.id, name="Відпустка", target_amount=20000, current_amount=7000),
                Debt(user_id=user.id, name="Кредит", total_amount=10000, remaining_amount=4000),
                MerchantCategory(user_id=user.id, merchant_key="атб", category_id=food.id),
            ])
            await db.commit()
            return user.id
    return client.portal.call(_seed)


async def _user(db):
    return (await db.execute(select(User).where(User.telegram_id == TG))).scalar_one()


async def _count(db, model, user_id=None):
    stmt = select(func.count()).select_from(model)
    if user_id is not None:
        stmt = stmt.where(model.user_id == user_id)
    return (await db.execute(stmt)).scalar_one()


async def _accounts(db, user_id):
    return {a.name: a for a in (await db.execute(select(Account).where(Account.user_id == user_id))).scalars()}


def buttons(markup):
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row] if markup else []


def test_full_reset_flow_keeps_setup_and_sets_start_balances(client, state):
    uid = seed(client)
    bot = FakeBot()
    db_user = q(client, _user)
    host = FakeMessage(bot, message_id=77)

    client.portal.call(rh.reset_start, FakeCallback(bot, "reset:start", host), db_user, state)
    warn = host.edits[-1]["text"]
    assert "2 транзакций" in warn and "1 переводов" in warn and "Monobank, Долари" in warn and "СБРОСИТЬ" in warn
    assert q(client, lambda db: _count(db, Transaction, uid)) == 2           # ще нічого не видалено

    client.portal.call(rh.reset_confirm, FakeMessage(bot, text="сбросить"), db_user, state)
    for model in (Transaction, Transfer, WalletPending):
        assert q(client, lambda db: _count(db, model, uid)) == 0
    assert q(client, lambda db: _count(db, Transaction)) == 1                # чужі дані не чіпаємо
    accs = q(client, lambda db: _accounts(db, uid))
    assert {n: a.balance for n, a in accs.items()} == {"Monobank": 0.0, "Долари": 0.0}
    budget = q(client, lambda db: _first(db, Budget))
    assert (budget.limit_amount, budget.spent_amount) == (3000, 0)
    goal = q(client, lambda db: _first(db, Goal))
    assert (goal.target_amount, goal.current_amount) == (20000, 0)
    assert q(client, lambda db: _first(db, Debt)).remaining_amount == 4000   # борги — як є
    assert q(client, lambda db: _count(db, Category, uid)) == 1
    assert q(client, lambda db: _count(db, MerchantCategory, uid)) == 1
    assert q(client, _user).history_reset_at is not None

    ask = bot.edited[-1]
    assert ask["message_id"] == 77 and "Monobank" in ask["text"] and "ещё 1" in ask["text"]
    assert buttons(ask["markup"]) == [("0", "reset:zero")]

    client.portal.call(rh.reset_balance, FakeMessage(bot, text="abc"), state)  # не число — питаємо ще
    client.portal.call(rh.reset_balance, FakeMessage(bot, text="12 500,50"), state)
    assert "Долари" in bot.edited[-1]["text"] and "(USD)" in bot.edited[-1]["text"]
    client.portal.call(rh.reset_zero, FakeCallback(bot, "reset:zero", FakeMessage(bot, message_id=77)), state)

    accs = q(client, lambda db: _accounts(db, uid))
    assert accs["Monobank"].balance == pytest.approx(12500.5) and accs["Долари"].balance == 0
    final = bot.edited[-1]["text"]
    assert "Старт" in final and "12 500,50 ₴" in final and "0,00 $" in final
    assert client.portal.call(state.get_state) is None
    assert q(client, lambda db: _accounts(db, uid + 1))["Чужий"].balance == 999.0


async def _first(db, model):
    return (await db.execute(select(model))).scalars().first()


def test_wrong_word_or_cancel_changes_nothing(client, state):
    uid = seed(client)
    bot = FakeBot()
    db_user = q(client, _user)
    host = FakeMessage(bot, message_id=77)
    client.portal.call(rh.reset_start, FakeCallback(bot, "reset:start", host), db_user, state)
    client.portal.call(rh.reset_confirm, FakeMessage(bot, text="так"), db_user, state)
    assert "Не подтверждено" in bot.edited[-1]["text"]
    assert q(client, lambda db: _count(db, Transaction, uid)) == 2
    assert client.portal.call(state.get_state) is None

    client.portal.call(rh.reset_start, FakeCallback(bot, "reset:start", host), db_user, state)
    client.portal.call(rh.reset_cancel, FakeCallback(bot, "reset:cancel", host), state)
    assert "Отменено" in host.edits[-1]["text"]
    assert q(client, lambda db: _count(db, Transaction, uid)) == 2
    assert q(client, _user).history_reset_at is None


def test_reset_drops_pending_monobank_confirms():
    mono._pending.clear()
    mono._pending.update({"1": {"user_id": 7}, "2": {"user_id": 8}})
    mono.drop_user_pending(7)
    assert list(mono._pending) == ["2"]
    mono._pending.clear()


def test_monobank_items_before_reset_are_skipped(client, monkeypatch):
    """Reconciliation перечитує останні години — старі операції не повертаються після скидання."""
    from app.models import BankConnection, BankCard
    uid = seed(client)
    reset_at = datetime.utcnow()

    async def _setup(db):
        user = await db.get(User, uid)
        user.history_reset_at = reset_at
        acc = (await _accounts(db, uid))["Monobank"]
        conn = BankConnection(user_id=uid, encrypted_token="x")
        db.add(conn)
        await db.flush()
        db.add(BankCard(connection_id=conn.id, mono_account_id="m1", account_id=acc.id, is_tracked=True,
                        currency_code=980))
        await db.commit()
        return conn.id

    conn_id = q(client, _setup)
    sent = []
    monkeypatch.setattr(mono, "_register_pending", lambda data: sent.append(data) or "p")

    async def fake_match(**kw):
        return {"new_name": "Інше"}

    monkeypatch.setattr(mono, "match_category", fake_match)
    import bot.main as bot_main

    class Bot:
        async def send_message(self, *a, **kw):
            pass

    monkeypatch.setattr(bot_main, "bot", Bot())
    # history_reset_at — наївний UTC; time у виписці — unix-секунди
    from datetime import timezone
    old = {"id": "old", "amount": -1000, "description": "АТБ", "mcc": 5411, "hold": False, "currencyCode": 980}
    new = {**old, "id": "new"}
    old["time"] = int((reset_at - timedelta(hours=1)).replace(tzinfo=timezone.utc).timestamp())
    new["time"] = int((reset_at + timedelta(minutes=5)).replace(tzinfo=timezone.utc).timestamp())
    client.portal.call(mono._process_statement_item, conn_id, "m1", old)
    assert sent == []
    client.portal.call(mono._process_statement_item, conn_id, "m1", new)
    assert len(sent) == 1 and sent[0]["external_id"] == "new"
