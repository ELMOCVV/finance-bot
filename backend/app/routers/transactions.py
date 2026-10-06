from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Transaction, Account
from app.schemas.transaction import TransactionCreate, TransactionUpdate, TransactionResponse
from app.services.transaction_service import create_transaction_record

router = APIRouter(prefix="/transactions", tags=["transactions"])


async def _get_user_transaction(transaction_id: int, user_id: int, db: AsyncSession) -> Transaction:
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.user_id == user_id)
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Транзакцію не знайдено")
    return tx


@router.get("/", response_model=list[TransactionResponse])
async def list_transactions(
    user_id: int = Query(...),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    type: Optional[str] = Query(None),
    account_id: Optional[int] = Query(None),
    category_id: Optional[int] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Список транзакцій користувача з фільтрацією."""
    filters = [Transaction.user_id == user_id]
    if type:
        filters.append(Transaction.type == type)
    if account_id:
        filters.append(Transaction.account_id == account_id)
    if category_id:
        filters.append(Transaction.category_id == category_id)
    if date_from:
        filters.append(Transaction.date >= date_from)
    if date_to:
        filters.append(Transaction.date <= date_to)

    result = await db.execute(
        select(Transaction)
        .where(and_(*filters))
        .order_by(Transaction.date.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("/", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    user_id: int = Query(...),
    payload: TransactionCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    """Додати нову транзакцію."""
    # Перевірка рахунку
    acc_result = await db.execute(
        select(Account).where(and_(Account.id == payload.account_id, Account.user_id == user_id))
    )
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Рахунок не знайдено")

    return await create_transaction_record(
        db,
        user_id=user_id,
        account=account,
        type=payload.type,
        amount=payload.amount,
        currency=payload.currency,
        category_id=payload.category_id,
        description=payload.description,
        date=payload.date,
        source=payload.source,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await _get_user_transaction(transaction_id, user_id, db)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: int,
    user_id: int = Query(...),
    payload: TransactionUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    tx = await _get_user_transaction(transaction_id, user_id, db)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(tx, field, value)
    await db.flush()
    await db.refresh(tx)
    return tx


@router.delete("/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    tx = await _get_user_transaction(transaction_id, user_id, db)
    # Повертаємо баланс рахунку
    acc_result = await db.execute(select(Account).where(Account.id == tx.account_id))
    account = acc_result.scalar_one_or_none()
    if account:
        if tx.type == "income":
            account.balance -= tx.amount
        elif tx.type in ("expense", "debt_payment"):
            account.balance += tx.amount
    await db.delete(tx)
