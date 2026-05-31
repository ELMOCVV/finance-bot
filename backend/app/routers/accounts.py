from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Account
from app.schemas.account import AccountCreate, AccountUpdate, AccountResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def _get_user_account(account_id: int, user_id: int, db: AsyncSession) -> Account:
    result = await db.execute(
        select(Account).where(and_(Account.id == account_id, Account.user_id == user_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Рахунок не знайдено")
    return account


@router.get("/", response_model=list[AccountResponse])
async def list_accounts(
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Account).where(Account.user_id == user_id))
    return result.scalars().all()


@router.post("/", response_model=AccountResponse, status_code=201)
async def create_account(
    user_id: int = Query(...),
    payload: AccountCreate = ...,
    db: AsyncSession = Depends(get_db),
):
    # Якщо новий рахунок is_default — знімаємо прапор з інших
    if payload.is_default:
        result = await db.execute(
            select(Account).where(and_(Account.user_id == user_id, Account.is_default == True))
        )
        for acc in result.scalars().all():
            acc.is_default = False

    account = Account(user_id=user_id, **payload.model_dump())
    db.add(account)
    await db.flush()
    await db.refresh(account)
    return account


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await _get_user_account(account_id, user_id, db)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    user_id: int = Query(...),
    payload: AccountUpdate = ...,
    db: AsyncSession = Depends(get_db),
):
    account = await _get_user_account(account_id, user_id, db)
    if payload.is_default:
        result = await db.execute(
            select(Account).where(
                and_(Account.user_id == user_id, Account.is_default == True, Account.id != account_id)
            )
        )
        for acc in result.scalars().all():
            acc.is_default = False
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(account, field, value)
    await db.flush()
    await db.refresh(account)
    return account


@router.delete("/{account_id}", status_code=204)
async def delete_account(
    account_id: int,
    user_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_user_account(account_id, user_id, db)
    await db.delete(account)
