from datetime import datetime, date
from sqlalchemy import String, Float, ForeignKey, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Назва боргу (напр. "Іпотека ПриватБанк")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    remaining_amount: Mapped[float] = mapped_column(Float, nullable=False)
    monthly_payment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Відсоткова ставка річна (напр. 12.5 = 12.5%)
    interest_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    next_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Зв'язок
    user: Mapped["User"] = relationship("User", back_populates="debts")

    def __repr__(self) -> str:
        return (
            f"<Debt id={self.id} name={self.name!r} "
            f"remaining={self.remaining_amount} {self.currency}>"
        )
