"""«Почати з нуля»: повне скидання історії користувача без повторного налаштування.

Видаляє транзакції (витрати, доходи, розбиті витрати Wallet/Monobank), перекази
і відкладені витрати Wallet; обнуляє баланси рахунків, «витрачено» в бюджетах
та накопичене в цілях. Лишає рахунки, категорії, ліміти бюджетів, цілі, борги,
підписки, привʼязки карток, запамʼятовані категорії продавців і Monobank.
Записує users.history_reset_at — операції Monobank до цього моменту більше
не пропонуються (reconciliation-job перевіряє останні години).
Коміт — на боці викликача.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Goal, Transaction, Transfer, User, WalletPending


@dataclass
class ResetPreview:
    transactions: int
    transfers: int
    accounts: list[Account]


async def preview_reset(db: AsyncSession, user_id: int) -> ResetPreview:
    async def count(model) -> int:
        return (await db.execute(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )).scalar_one()

    accounts = (await db.execute(
        select(Account).where(Account.user_id == user_id).order_by(Account.id)
    )).scalars().all()
    return ResetPreview(await count(Transaction), await count(Transfer), list(accounts))


async def reset_user_history(db: AsyncSession, user: User) -> None:
    uid = user.id
    await db.execute(delete(Transaction).where(Transaction.user_id == uid))
    await db.execute(delete(Transfer).where(Transfer.user_id == uid))
    await db.execute(delete(WalletPending).where(WalletPending.user_id == uid))
    await db.execute(update(Account).where(Account.user_id == uid).values(balance=0.0))
    await db.execute(update(Budget).where(Budget.user_id == uid).values(spent_amount=0.0))
    await db.execute(update(Goal).where(Goal.user_id == uid).values(current_amount=0.0))
    user.history_reset_at = datetime.utcnow()
    await db.flush()
