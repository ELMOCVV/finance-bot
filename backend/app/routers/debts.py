from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Debt, Account, Transaction
from app.schemas.debt import DebtCreate, DebtUpdate, DebtResponse, DebtPaymentRequest
from app.services.exchange_rate_service import exchange_rate_service

router = APIRouter(prefix="/debts", tags=["debts"])


@router.get("/", response_model=list[DebtResponse])
async def list_debts(
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Debt).where(Debt.user_id == user_id).order_by(Debt.next_payment_date))
    return result.scalars().all()


@router.post("/", response_model=DebtResponse, status_code=201)
async def create_debt(
    user_id: int = Query(...),
    payload: DebtCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    debt = Debt(user_id=user_id, **payload.model_dump())
    db.add(debt)
    await db.flush()
    await db.refresh(debt)
    return debt


@router.get("/{debt_id}", response_model=DebtResponse)
async def get_debt(
    debt_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == user_id))
    )
    debt = result.scalar_one_or_none()
    if not debt:
        raise HTTPException(status_code=404, detail="Борг не знайдено")
    return debt


@router.patch("/{debt_id}", response_model=DebtResponse)
async def update_debt(
    debt_id: int,
    user_id: int = Query(...),
    payload: DebtUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == user_id))
    )
    debt = result.scalar_one_or_none()
    if not debt:
        raise HTTPException(status_code=404, detail="Борг не знайдено")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(debt, field, value)
    await db.flush()
    await db.refresh(debt)
    return debt


@router.post("/{debt_id}/payment", response_model=DebtResponse)
async def pay_debt(
    debt_id: int,
    user_id: int = Query(...),
    payload: DebtPaymentRequest = ...,
    db: AsyncSession = Depends(get_db),
):
    """Платіж по боргу: списує суму з рахунку та зменшує залишок боргу.

    Рахунок має належати тому ж користувачу, що й борг. Створює
    транзакцію type="debt_payment". Залишок боргу не опускається нижче 0
    (при повному погашенні remaining_amount = 0).
    """
    result = await db.execute(
        select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == user_id))
    )
    debt = result.scalar_one_or_none()
    if not debt:
        raise HTTPException(status_code=404, detail="Борг не знайдено")

    acc_result = await db.execute(
        select(Account).where(and_(Account.id == payload.account_id, Account.user_id == user_id))
    )
    account = acc_result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Рахунок не знайдено")

    amount_uah = await exchange_rate_service.to_uah(payload.amount, account.currency)
    db.add(Transaction(
        user_id=user_id,
        account_id=account.id,
        category_id=None,
        type="debt_payment",
        amount=payload.amount,
        currency=account.currency,
        amount_uah=amount_uah,
        description=f"Погашення боргу: {debt.name}",
        date=datetime.utcnow(),
        source="advisor_action",
    ))

    account.balance -= payload.amount
    debt.remaining_amount = max(0.0, debt.remaining_amount - payload.amount)

    await db.flush()
    await db.refresh(debt)
    return debt


@router.delete("/{debt_id}", status_code=204)
async def delete_debt(
    debt_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Debt).where(and_(Debt.id == debt_id, Debt.user_id == user_id))
    )
    debt = result.scalar_one_or_none()
    if not debt:
        raise HTTPException(status_code=404, detail="Борг не знайдено")
    await db.delete(debt)
