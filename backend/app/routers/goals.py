from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Goal
from app.schemas.goal import GoalCreate, GoalUpdate, GoalResponse

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("/", response_model=list[GoalResponse])
async def list_goals(
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Goal).where(Goal.user_id == user_id).order_by(Goal.deadline))
    return result.scalars().all()


@router.post("/", response_model=GoalResponse, status_code=201)
async def create_goal(
    user_id: int = Query(...),
    payload: GoalCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    goal = Goal(user_id=user_id, **payload.model_dump())
    db.add(goal)
    await db.flush()
    await db.refresh(goal)
    return goal


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Ціль не знайдено")
    return goal


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: int,
    user_id: int = Query(...),
    payload: GoalUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Ціль не знайдено")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(goal, field, value)
    await db.flush()
    await db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Goal).where(and_(Goal.id == goal_id, Goal.user_id == user_id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Ціль не знайдено")
    await db.delete(goal)
