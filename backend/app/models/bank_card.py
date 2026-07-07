from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class BankCard(Base):
    """Картка/рахунок Monobank, привʼязаний до внутрішнього рахунку (accounts).

    mono_account_id — ідентифікатор рахунку в Monobank (використовується
    для звірки вхідних webhook-подій). account_id вказує на локальний
    рахунок, що дзеркалить баланс. При видаленні локального рахунку
    account_id стає NULL — сама картка лишається.
    """
    __tablename__ = "bank_cards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("bank_connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mono_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    masked_pan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # ISO 4217 числовий код валюти (980 = UAH тощо)
    currency_code: Mapped[int] = mapped_column(nullable=False, default=980)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    is_tracked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Зв'язки
    connection: Mapped["BankConnection"] = relationship("BankConnection", back_populates="cards")
    account: Mapped["Account | None"] = relationship("Account")

    def __repr__(self) -> str:
        return (
            f"<BankCard id={self.id} mono_account_id={self.mono_account_id} "
            f"masked_pan={self.masked_pan!r} tracked={self.is_tracked}>"
        )
