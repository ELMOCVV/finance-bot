from datetime import datetime
from sqlalchemy import BigInteger, String, Float, Integer, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    # monthly | yearly
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    # День місяця списання (1-31)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False)
    # Місяць (1-12), тільки для yearly
    month_of_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Рахунок (опційно — при видаленні рахунку ставиться NULL)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    # Година надсилання нагадування (0-23)
    remind_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=9)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Зв'язки
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    account: Mapped["Account | None"] = relationship("Account")

    def __repr__(self) -> str:
        return f"<Subscription id={self.id} name={self.name!r} {self.amount} {self.currency}/{self.period}>"
