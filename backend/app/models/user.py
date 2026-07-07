from datetime import datetime
from sqlalchemy import BigInteger, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Зв'язки
    accounts: Mapped[list["Account"]] = relationship("Account", back_populates="user", cascade="all, delete-orphan")
    categories: Mapped[list["Category"]] = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    transfers: Mapped[list["Transfer"]] = relationship("Transfer", back_populates="user", cascade="all, delete-orphan")
    debts: Mapped[list["Debt"]] = relationship("Debt", back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["Goal"]] = relationship("Goal", back_populates="user", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    bank_connections: Mapped[list["BankConnection"]] = relationship("BankConnection", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id} username={self.username!r}>"
