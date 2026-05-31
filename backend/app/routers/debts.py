from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Debt
from app.schemas.debt import DebtCreate, DebtUpdate, DebtResponse

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
