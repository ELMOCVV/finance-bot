from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    User, Account, Transaction, Transfer, Goal, Debt, Budget,
    BankConnection, BankCard,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/{user_id}/reset-all-data")
async def reset_all_data(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Скидання всіх даних користувача.

    Видаляє транзакції, перекази, цілі, борги, бюджети та повністю відключає
    Monobank (картки + з'єднання). Рахунки і категорії лишаються, але баланси
    всіх рахунків обнуляються. Усе — в межах однієї транзакції (get_db робить
    commit лише при успішному поверненні, інакше rollback), тож або все
    відбувається, або нічого.
    """
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    tx_count = (await db.execute(
        delete(Transaction).where(Transaction.user_id == user_id)
    )).rowcount
    transfer_count = (await db.execute(
        delete(Transfer).where(Transfer.user_id == user_id)
    )).rowcount
    goal_count = (await db.execute(
        delete(Goal).where(Goal.user_id == user_id)
    )).rowcount
    debt_count = (await db.execute(
        delete(Debt).where(Debt.user_id == user_id)
    )).rowcount
    budget_count = (await db.execute(
        delete(Budget).where(Budget.user_id == user_id)
    )).rowcount

    # Monobank: спершу картки, потім з'єднання (без опори на DB-каскад).
    conn_ids = select(BankConnection.id).where(BankConnection.user_id == user_id)
    await db.execute(delete(BankCard).where(BankCard.connection_id.in_(conn_ids)))
    connection_count = (await db.execute(
        delete(BankConnection).where(BankConnection.user_id == user_id)
    )).rowcount

    # Рахунки лишаються — лише обнуляємо баланси.
    accounts_zeroed = (await db.execute(
        update(Account).where(Account.user_id == user_id).values(balance=0.0)
    )).rowcount

    return {
        "transactions": tx_count,
        "transfers": transfer_count,
        "goals": goal_count,
        "debts": debt_count,
        "budgets": budget_count,
        "bank_connections": connection_count,
        "accounts_zeroed": accounts_zeroed,
    }
