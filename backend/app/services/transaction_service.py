"""Спільна логіка створення транзакції в межах переданої сесії.

Використовується REST-роутером транзакцій і webhook-ом Apple Wallet:
створює Transaction, конвертує суму в UAH, оновлює баланс рахунку та
витрачену суму бюджету (для витрат з категорією). Коміт — на боці викликача.
"""
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Transaction, Account, Budget
from app.services.exchange_rate_service import exchange_rate_service


async def create_transaction_record(
    db: AsyncSession,
    *,
    user_id: int,
    account: Account,
    type: str,
    amount: float,
    currency: str,
    category_id: int | None = None,
    description: str | None = None,
    date: datetime | None = None,
    source: str = "manual",
    merchant: str | None = None,
    card: str | None = None,
) -> Transaction:
    # Конвертація в UAH
    amount_uah = await exchange_rate_service.to_uah(amount, currency)
    tx_date = date or datetime.utcnow()

    tx = Transaction(
        user_id=user_id,
        account_id=account.id,
        category_id=category_id,
        type=type,
        amount=amount,
        currency=currency,
        amount_uah=amount_uah,
        description=description,
        date=tx_date,
        source=source,
        merchant=merchant,
        card=card,
    )
    db.add(tx)

    # Оновлення балансу рахунку
    if type == "income":
        account.balance += amount
    elif type in ("expense", "debt_payment"):
        account.balance -= amount

    # Оновлення витраченої суми в бюджеті
    if type == "expense" and category_id:
        month_str = tx_date.strftime("%Y-%m")
        budget_result = await db.execute(
            select(Budget).where(
                and_(
                    Budget.user_id == user_id,
                    Budget.category_id == category_id,
                    Budget.month == month_str,
                )
            )
        )
        budget = budget_result.scalar_one_or_none()
        if budget:
            budget.spent_amount += amount_uah

    await db.flush()
    await db.refresh(tx)
    return tx
