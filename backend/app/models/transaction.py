from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)

    # expense | income | debt_payment | transfer
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Валюта транзакції (може відрізнятись від рахунку)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    # Сума в гривнях (для уніфікованої аналітики)
    amount_uah: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    # manual | bot_text | bot_photo | monobank | monobank_import | advisor_action
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    # Ідентифікатор операції у зовнішньому джерелі (напр. Monobank statementItem.id)
    # для дедуплікації між webhook і reconciliation-job.
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Зв'язки
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    account: Mapped["Account"] = relationship("Account", back_populates="transactions")
    category: Mapped["Category | None"] = relationship("Category", back_populates="transactions")

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.id} type={self.type} "
            f"amount={self.amount} {self.currency} date={self.date}>"
        )
