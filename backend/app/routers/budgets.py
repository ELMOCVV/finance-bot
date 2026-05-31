from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Budget
from app.schemas.budget import BudgetCreate, BudgetUpdate, BudgetResponse

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("/", response_model=list[BudgetResponse])
async def list_budgets(
    user_id: int = Query(...),
    month: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = [Budget.user_id == user_id]
    if month:
        filters.append(Budget.month == month)
    result = await db.execute(select(Budget).where(and_(*filters)))
    return result.scalars().all()


@router.post("/", response_model=BudgetResponse, status_code=201)
async def create_budget(
    user_id: int = Query(...),
    payload: BudgetCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    # Перевірка дублювання бюджету для цієї категорії/місяця
    existing = await db.execute(
        select(Budget).where(
            and_(
                Budget.user_id == user_id,
                Budget.category_id == payload.category_id,
                Budget.month == payload.month,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Бюджет для цієї категорії вже існує")

    budget = Budget(user_id=user_id, **payload.model_dump())
    db.add(budget)
    await db.flush()
    await db.refresh(budget)
    return budget


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: int,
    user_id: int = Query(...),
    payload: BudgetUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Budget).where(and_(Budget.id == budget_id, Budget.user_id == user_id))
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Бюджет не знайдено")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(budget, field, value)
    await db.flush()
    await db.refresh(budget)
    return budget


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(
    budget_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Budget).where(and_(Budget.id == budget_id, Budget.user_id == user_id))
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Бюджет не знайдено")
    await db.delete(budget)
