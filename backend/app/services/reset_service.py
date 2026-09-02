"""Повне скидання фінансових даних користувача.

Видаляє транзакції, перекази, цілі, борги, бюджети та банківські підключення
(Monobank — разом з картками). Рахунки й категорії лишаються: рахунки
зберігають назву/валюту/ключові слова, але їхні баланси обнуляються.
Підписки та сам користувач не зачіпаються.

Уся операція виконується в одній транзакції: або застосовується повністю,
або не застосовується взагалі.
"""
import logging

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Account, Transaction, Transfer, Goal, Debt, Budget, BankCard, BankConnection,
)

logger = logging.getLogger(__name__)

# Моделі, рядки яких видаляються цілком (усі мають user_id).
_DELETE_MODELS = (
    ("transactions", Transaction),
    ("transfers",    Transfer),
    ("goals",        Goal),
    ("debts",        Debt),
    ("budgets",      Budget),
)


async def _count(db: AsyncSession, model, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )
    return int(result.scalar_one() or 0)


async def reset_all_data(user_id: int, db: AsyncSession) -> dict:
    """Скидає всі дані користувача і повертає підсумок операції.

    Повертає dict з кількістю видалених рядків по кожній сутності та
    кількістю рахунків, баланси яких обнулено. При будь-якій помилці
    транзакція відкочується і виняток пробрасується далі — часткового
    скидання статись не може.
    """
    try:
        summary = {name: await _count(db, model, user_id) for name, model in _DELETE_MODELS}
        summary["bank_connections"] = await _count(db, BankConnection, user_id)
        summary["accounts_reset"] = await _count(db, Account, user_id)

        for _, model in _DELETE_MODELS:
            await db.execute(delete(model).where(model.user_id == user_id))

        # Картки видаляємо явно: у SQLite перевірка зовнішніх ключів вимкнена
        # за замовчуванням, тож покладатись на ondelete=CASCADE не можна.
        conn_ids = select(BankConnection.id).where(BankConnection.user_id == user_id)
        await db.execute(delete(BankCard).where(BankCard.connection_id.in_(conn_ids)))
        await db.execute(delete(BankConnection).where(BankConnection.user_id == user_id))

        # Рахунки лишаються — обнуляємо тільки баланси.
        await db.execute(
            update(Account).where(Account.user_id == user_id).values(balance=0.0)
        )

        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Скидання даних не вдалось (user_id=%s) — зміни відкочено", user_id)
        raise

    logger.info("Дані користувача скинуто (user_id=%s): %s", user_id, summary)
    return summary
