from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models import User, Account, Category, Transaction
from app.services import transaction_service
from conftest import wipe_db

SECRET = "test-secret"
OWNER_TG_ID = 777000111


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def setup(client, monkeypatch):
    monkeypatch.setattr(settings, "WALLET_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "WALLET_OWNER_TG_ID", str(OWNER_TG_ID))

    # Без мережі: курс 1:40 для не-UAH
    async def fake_to_uah(amount, currency):
        return amount if currency == "UAH" else amount * 40

    monkeypatch.setattr(transaction_service.exchange_rate_service, "to_uah", fake_to_uah)
    client.portal.call(_reset_db)


async def _reset_db():
    await wipe_db()
    async with AsyncSessionLocal() as db:
        user = User(telegram_id=OWNER_TG_ID, first_name="Owner")
        db.add(user)
        await db.flush()
        db.add_all([
            Account(user_id=user.id, name="Готівка", currency="UAH", balance=1000.0, is_default=True),
            Account(user_id=user.id, name="Monobank Black", currency="UAH", balance=5000.0),
            Category(user_id=user.id, name="Їжа", type="expense"),
            Category(user_id=user.id, name="Інше", type="expense"),
            Category(user_id=user.id, name="Інше", type="income"),
        ])
        await db.commit()


def _call(client, portal_fn):
    return client.portal.call(portal_fn)


async def _all_txs():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Transaction).order_by(Transaction.id))).scalars().all()


async def _tx_count():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count(Transaction.id)))).scalar_one()


def _post(client, body, token=SECRET):
    headers = {"X-Token": token} if token is not None else {}
    return client.post("/api/wallet-tx", json=body, headers=headers)


def test_valid_token_creates_expense(client):
    r = _post(client, {"amount": "1 250,50 ₴", "merchant": "АТБ", "card": "monobank"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True and isinstance(data["id"], int)

    (tx,) = _call(client, _all_txs)
    assert tx.id == data["id"]
    assert tx.type == "expense"
    assert tx.amount == 1250.50 and tx.currency == "UAH" and tx.amount_uah == 1250.50
    assert tx.merchant == "АТБ" and tx.card == "monobank" and tx.description == "АТБ"
    assert tx.source == "wallet"
    assert abs(datetime.utcnow() - tx.date) < timedelta(minutes=1)

    async def check():
        async with AsyncSessionLocal() as db:
            acc = await db.get(Account, tx.account_id)
            cat = await db.get(Category, tx.category_id)
            return acc.name, acc.balance, cat.name

    acc_name, balance, cat_name = _call(client, check)
    assert acc_name == "Monobank Black"           # рахунок підібрано за назвою картки
    assert balance == 5000.0 - 1250.50            # баланс оновлено спільною логікою
    assert cat_name == "Їжа"                      # АТБ → Їжа за словником


def test_unknown_merchant_falls_back_to_other_and_default_account(client):
    r = _post(client, {"amount": "12,99 €", "merchant": "Some Shop GmbH", "card": "Revolut"})
    assert r.status_code == 200, r.text
    (tx,) = _call(client, _all_txs)
    assert tx.currency == "EUR" and tx.amount == 12.99 and tx.amount_uah == pytest.approx(12.99 * 40)

    async def check():
        async with AsyncSessionLocal() as db:
            return (await db.get(Account, tx.account_id)).name, (await db.get(Category, tx.category_id)).name

    assert _call(client, check) == ("Готівка", "Інше")


@pytest.mark.parametrize("token", ["wrong", "", None])
def test_invalid_token_403(client, token):
    r = _post(client, {"amount": "250,00 ₴", "merchant": "АТБ", "card": "monobank"}, token=token)
    assert r.status_code == 403
    assert _call(client, _tx_count) == 0


def test_secret_not_configured_403(client, monkeypatch):
    monkeypatch.setattr(settings, "WALLET_WEBHOOK_SECRET", "")
    r = _post(client, {"amount": "250,00 ₴", "merchant": "АТБ", "card": "monobank"}, token="")
    assert r.status_code == 403
    assert _call(client, _tx_count) == 0


def test_broken_amount_422_and_logged(client, caplog):
    caplog.set_level("INFO", logger="app.routers.wallet_webhook")
    r = _post(client, {"amount": "сто гривень", "merchant": "АТБ", "card": "monobank"})
    assert r.status_code == 422
    assert _call(client, _tx_count) == 0
    assert "сто гривень" in caplog.text
    assert SECRET not in caplog.text


def test_invalid_json_422(client):
    r = client.post("/api/wallet-tx", content=b"not json", headers={"X-Token": SECRET})
    assert r.status_code == 422


def test_duplicate_within_60s_returns_same_id(client):
    body = {"amount": "250,00 ₴", "merchant": "АТБ", "card": "monobank"}
    first = _post(client, body)
    second = _post(client, {"amount": "₴250.00", "merchant": "АТБ", "card": "monobank"})
    assert first.status_code == second.status_code == 200
    assert second.json() == {"ok": True, "id": first.json()["id"]}
    assert _call(client, _tx_count) == 1

    # Інша картка — це вже інша операція
    third = _post(client, {**body, "card": "privat"})
    assert third.json()["id"] != first.json()["id"]
    assert _call(client, _tx_count) == 2


def test_same_payment_after_60s_is_not_duplicate(client):
    body = {"amount": "250,00 ₴", "merchant": "АТБ", "card": "monobank"}
    first_id = _post(client, body).json()["id"]

    async def age_tx():
        async with AsyncSessionLocal() as db:
            tx = await db.get(Transaction, first_id)
            tx.date = datetime.utcnow() - timedelta(seconds=61)
            await db.commit()

    _call(client, age_tx)
    second_id = _post(client, body).json()["id"]
    assert second_id != first_id
    assert _call(client, _tx_count) == 2


def test_raw_body_logged_without_token(client, caplog):
    caplog.set_level("INFO", logger="app.routers.wallet_webhook")
    _post(client, {"amount": "5 ₴", "merchant": "Кафе", "card": "mono"})
    assert "Wallet webhook raw body" in caplog.text
    assert "Кафе" in caplog.text
    assert SECRET not in caplog.text
