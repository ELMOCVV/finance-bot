"""Регресія: POST /api/v1/transactions/ після винесення логіки в transaction_service."""
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.main import app
from app.models import User, Account, Category, Budget, Transaction
from app.services import transaction_service


def test_create_expense_updates_balance_and_budget(monkeypatch):
    async def fake_to_uah(amount, currency):
        return amount

    monkeypatch.setattr(transaction_service.exchange_rate_service, "to_uah", fake_to_uah)

    with TestClient(app) as client:
        async def seed():
            async with AsyncSessionLocal() as db:
                user = User(telegram_id=555000222)
                db.add(user)
                await db.flush()
                acc = Account(user_id=user.id, name="Card", balance=100.0)
                cat = Category(user_id=user.id, name="Їжа", type="expense")
                db.add_all([acc, cat])
                await db.flush()
                db.add(Budget(user_id=user.id, category_id=cat.id,
                              month=datetime.utcnow().strftime("%Y-%m"), limit_amount=500.0))
                await db.commit()
                return user.id, acc.id, cat.id

        user_id, acc_id, cat_id = client.portal.call(seed)
        r = client.post(
            f"/api/v1/transactions/?user_id={user_id}",
            json={"account_id": acc_id, "category_id": cat_id, "type": "expense",
                  "amount": 30, "description": "обід"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["amount"] == 30 and body["source"] == "manual" and body["description"] == "обід"

        async def check():
            async with AsyncSessionLocal() as db:
                acc = await db.get(Account, acc_id)
                budget = (await db.execute(select(Budget).where(Budget.user_id == user_id))).scalar_one()
                tx = await db.get(Transaction, body["id"])
                return acc.balance, budget.spent_amount, tx.merchant

        assert client.portal.call(check) == (70.0, 30.0, None)
