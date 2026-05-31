from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def get_summary(
    user_id: int = Query(...),
    month: str = Query(default_factory=lambda: datetime.utcnow().strftime("%Y-%m")),
    db: AsyncSession = Depends(get_db),
):
    """Зведення за місяць: доходи, витрати, баланс."""
    return await analytics_service.get_summary(db, user_id, month)


@router.get("/by-category")
async def get_expenses_by_category(
    user_id: int = Query(...),
    month: str = Query(default_factory=lambda: datetime.utcnow().strftime("%Y-%m")),
    db: AsyncSession = Depends(get_db),
):
    """Розподіл витрат по категоріях."""
    return await analytics_service.get_expenses_by_category(db, user_id, month)


@router.get("/trend")
async def get_monthly_trend(
    user_id: int = Query(...),
    months: int = Query(6, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """Тренд доходів і витрат за останні N місяців."""
    return await analytics_service.get_monthly_trend(db, user_id, months)


@router.get("/budgets")
async def get_budget_status(
    user_id: int = Query(...),
    month: str = Query(default_factory=lambda: datetime.utcnow().strftime("%Y-%m")),
    db: AsyncSession = Depends(get_db),
):
    """Статус виконання бюджетів за місяць."""
    return await analytics_service.get_budget_status(db, user_id, month)
