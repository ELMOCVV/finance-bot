"""Спільна логіка транзакцій у межах переданої сесії.

create_transaction_record — використовується REST-роутером транзакцій і
webhook-ом Apple Wallet: створює Transaction, конвертує суму в UAH, оновлює
баланс рахунку та витрачену суму бюджету (для витрат з категорією).
delete / change_category / move_account — обернені та коригувальні дії
з тим самим перерахунком балансу й бюджету. Коміт — на боці викликача.
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
    account.balance += _balance_delta(type, amount)

    # Оновлення витраченої суми в бюджеті
    await _adjust_budget(db, user_id, type, category_id, tx_date, amount_uah)

    await db.flush()
    await db.refresh(tx)
    return tx


def _balance_delta(tx_type: str, amount: float) -> float:
    """Як транзакція змінює баланс рахунку."""
    if tx_type == "income":
        return amount
    if tx_type in ("expense", "debt_payment"):
        return -amount
    return 0.0


async def _adjust_budget(
    db: AsyncSession, user_id: int, tx_type: str, category_id: int | None,
    tx_date: datetime, amount_uah: float,
) -> None:
    """Додає amount_uah (може бути відʼємним) до бюджету категорії за місяць транзакції."""
    if tx_type != "expense" or not category_id:
        return
    budget_result = await db.execute(
        select(Budget).where(
            and_(
                Budget.user_id == user_id,
                Budget.category_id == category_id,
                Budget.month == tx_date.strftime("%Y-%m"),
            )
        )
    )
    budget = budget_result.scalar_one_or_none()
    if budget:
        budget.spent_amount += amount_uah


async def delete_transaction_record(db: AsyncSession, tx: Transaction) -> None:
    """Видаляє транзакцію, повертаючи баланс рахунку і витрачене по бюджету."""
    account = await db.get(Account, tx.account_id)
    if account:
        account.balance -= _balance_delta(tx.type, tx.amount)
    await _adjust_budget(db, tx.user_id, tx.type, tx.category_id, tx.date, -tx.amount_uah)
    await db.delete(tx)
    await db.flush()


async def change_transaction_category(db: AsyncSession, tx: Transaction, category_id: int | None) -> None:
    """Змінює категорію: бюджет старої категорії мінус, нової — плюс."""
    if tx.category_id == category_id:
        return
    await _adjust_budget(db, tx.user_id, tx.type, tx.category_id, tx.date, -tx.amount_uah)
    await _adjust_budget(db, tx.user_id, tx.type, category_id, tx.date, tx.amount_uah)
    tx.category_id = category_id
    await db.flush()


async def move_transaction_account(db: AsyncSession, tx: Transaction, new_account: Account) -> None:
    """Переносить транзакцію на інший рахунок: повертає суму на старий, списує з нового."""
    if tx.account_id == new_account.id:
        return
    old_account = await db.get(Account, tx.account_id)
    delta = _balance_delta(tx.type, tx.amount)
    if old_account:
        old_account.balance -= delta
    new_account.balance += delta
    tx.account_id = new_account.id
    await db.flush()
