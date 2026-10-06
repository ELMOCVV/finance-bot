"""Довідники Apple Wallet: запамʼятовані категорії продавців, привʼязки
карток до рахунків і відкладені витрати (коли в користувача ще немає рахунків).

Ключі (merchant_key / card_key) — нормалізовані назви в нижньому регістрі,
див. app.services.wallet_service.normalize_key.
"""
from datetime import datetime

from sqlalchemy import String, Float, ForeignKey, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MerchantCategory(Base):
    """Продавець → категорія, обрана користувачем вручну в боті."""
    __tablename__ = "wallet_merchant_categories"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key", name="uq_wallet_merchant_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_key: Mapped[str] = mapped_column(String(128), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


class WalletCard(Base):
    """Назва картки з Wallet (після очистки) → рахунок."""
    __tablename__ = "wallet_cards"
    __table_args__ = (UniqueConstraint("user_id", "card_key", name="uq_wallet_card_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    card_name: Mapped[str] = mapped_column(String(64), nullable=False)
    card_key: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)


class WalletPending(Base):
    """Витрата з Wallet, яку ще нікуди записати (у користувача немає рахунків)."""
    __tablename__ = "wallet_pending"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    merchant: Mapped[str | None] = mapped_column(String(128), nullable=True)
    card: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
