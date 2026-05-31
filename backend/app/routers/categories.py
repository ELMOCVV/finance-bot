from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("/", response_model=list[CategoryResponse])
async def list_categories(
    user_id: int = Query(...),
    type: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    filters = [Category.user_id == user_id]
    if type:
        filters.append(Category.type == type)
    result = await db.execute(select(Category).where(and_(*filters)).order_by(Category.name))
    return result.scalars().all()


@router.post("/", response_model=CategoryResponse, status_code=201)
async def create_category(
    user_id: int = Query(...),
    payload: CategoryCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    category = Category(user_id=user_id, **payload.model_dump())
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    user_id: int = Query(...),
    payload: CategoryUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(and_(Category.id == category_id, Category.user_id == user_id))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Категорію не знайдено")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(category, field, value)
    await db.flush()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(and_(Category.id == category_id, Category.user_id == user_id))
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Категорію не знайдено")
    await db.delete(category)
