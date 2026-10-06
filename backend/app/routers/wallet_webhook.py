"""Apple Wallet webhook.

POST /api/wallet-tx — автоматизація iOS «Команди» (тригер Wallet) надсилає
кожну оплату Apple Pay: {"amount": "250,00 ₴", "merchant": "АТБ", "card": "monobank"}
із секретом у заголовку X-Token. Операція записується як витрата
власника (WALLET_OWNER_TG_ID) з source="wallet" і status="pending", після чого
бот (у фоні) надсилає власнику повідомлення з кнопками підтвердження.
Якщо в користувача ще немає рахунків — дані зберігаються як WalletPending,
а бот пропонує створити рахунок.
"""
import json
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User, Account, Category, WalletPending
from app.schemas.wallet import WalletTxIn, WalletTxOut
from app.services.transaction_service import create_transaction_record
from app.services.wallet_notify import notify_in_background
from app.services.wallet_service import (
    WALLET_SOURCE, parse_wallet_amount, pick_category, pick_account, find_recent_duplicate,
    find_recent_pending_duplicate, clean_card, get_card_binding, get_remembered_category_id,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["wallet"])

_MAX_LOGGED_BODY = 2000


def _check_token(token: str | None) -> None:
    secret = settings.WALLET_WEBHOOK_SECRET
    if not secret or not token or not secrets.compare_digest(token.encode(), secret.encode()):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/wallet-tx", response_model=WalletTxOut, response_model_exclude_none=True)
async def receive_wallet_tx(request: Request, db: AsyncSession = Depends(get_db)) -> WalletTxOut:
    raw = await request.body()
    # Сире тіло (токен — у заголовку, сюди не потрапляє). %r — щоб бачити NBSP тощо.
    logger.info("Wallet webhook raw body: %r", raw[:_MAX_LOGGED_BODY].decode("utf-8", "replace"))

    _check_token(request.headers.get("X-Token"))

    try:
        payload = WalletTxIn.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as e:
        logger.warning("Wallet webhook: invalid body (%s)", e.__class__.__name__)
        raise HTTPException(status_code=422, detail="Invalid body")

    try:
        amount_dec, currency = parse_wallet_amount(payload.amount)
    except ValueError:
        logger.warning("Wallet webhook: cannot parse amount %r", payload.amount)
        raise HTTPException(status_code=422, detail="Cannot parse amount")
    amount = float(amount_dec)
    merchant = payload.merchant[:128] if payload.merchant else None
    card = clean_card(payload.card, merchant)
    card = card[:64] if card else None
    if payload.card != card:
        logger.info("Wallet webhook: card %r cleaned to %r", payload.card, card)

    try:
        owner_tg_id = int(settings.WALLET_OWNER_TG_ID)
    except ValueError:
        logger.error("Wallet webhook: WALLET_OWNER_TG_ID is not set or invalid")
        raise HTTPException(status_code=503, detail="Wallet webhook is not configured")
    user = (await db.execute(select(User).where(User.telegram_id == owner_tg_id))).scalar_one_or_none()
    if not user:
        logger.error("Wallet webhook: owner user not found (telegram_id=%s)", owner_tg_id)
        raise HTTPException(status_code=503, detail="Wallet webhook is not configured")

    # Дедуп: iOS інколи запускає автоматизацію двічі на одну оплату
    duplicate = await find_recent_duplicate(db, user.id, amount, merchant, card)
    if duplicate:
        logger.info("Wallet webhook: duplicate within 60s — skip (tx_id=%s)", duplicate.id)
        return WalletTxOut(id=duplicate.id)

    accounts = (await db.execute(select(Account).where(Account.user_id == user.id))).scalars().all()
    if not accounts:
        # Нікуди записати — відкладаємо, бот запропонує створити рахунок
        dup_pending = await find_recent_pending_duplicate(db, user.id, amount, merchant, card)
        if dup_pending:
            logger.info("Wallet webhook: duplicate pending within 60s — skip (pending_id=%s)", dup_pending.id)
            return WalletTxOut(pending_id=dup_pending.id)
        pending = WalletPending(user_id=user.id, amount=amount, currency=currency, merchant=merchant, card=card)
        db.add(pending)
        await db.commit()
        logger.info("Wallet webhook: no accounts — saved pending_id=%s", pending.id)
        notify_in_background("pending", pending.id)
        return WalletTxOut(id=None, pending_id=pending.id)

    # Привʼязана картка → її рахунок; інакше підказка за ключовими словами / за замовчуванням
    binding = await get_card_binding(db, user.id, card)
    account = next((a for a in accounts if binding and a.id == binding.account_id), None) or pick_account(card, accounts)

    cats_res = await db.execute(
        select(Category).where(and_(Category.user_id == user.id, Category.type == "expense"))
    )
    remembered_id = await get_remembered_category_id(db, user.id, merchant)
    category = pick_category(merchant, cats_res.scalars().all(), remembered_id)

    tx = await create_transaction_record(
        db,
        user_id=user.id,
        account=account,
        type="expense",
        amount=amount,
        currency=currency,
        category_id=category.id if category else None,
        description=merchant,
        source=WALLET_SOURCE,
        merchant=merchant,
        card=card,
    )
    tx.status = "pending"
    # Комітимо до відповіді: фонове надсилання читає витрату вже з нової сесії
    await db.commit()
    logger.info(
        "Wallet webhook: saved tx_id=%s %.2f %s account_id=%s card_bound=%s category=%s",
        tx.id, amount, currency, account.id, bool(binding), category.name if category else None,
    )
    notify_in_background("tx", tx.id)
    return WalletTxOut(id=tx.id)
