from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.schemas.reset import ResetSummaryResponse
from app.services.reset_service import reset_all_data

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/{user_id}/reset-all-data", response_model=ResetSummaryResponse)
async def reset_user_data(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Видаляє транзакції, перекази, цілі, борги, бюджети та підключення
    банків користувача; рахунки й категорії лишаються, баланси обнуляються."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    return await reset_all_data(user_id, db)
