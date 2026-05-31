from sqlalchemy import String, Float, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Валюта: UAH, USD, USDT тощо
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Ключові слова для автоматичного визначення рахунку з тексту
    keywords: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Зв'язки
    user: Mapped["User"] = relationship("User", back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="account")
    transfers_from: Mapped[list["Transfer"]] = relationship(
        "Transfer", foreign_keys="Transfer.from_account_id", back_populates="from_account"
    )
    transfers_to: Mapped[list["Transfer"]] = relationship(
        "Transfer", foreign_keys="Transfer.to_account_id", back_populates="to_account"
    )

    def __repr__(self) -> str:
        return f"<Account id={self.id} name={self.name!r} currency={self.currency} balance={self.balance}>"
