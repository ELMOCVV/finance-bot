from sqlalchemy import String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    # Місяць у форматі YYYY-MM
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    limit_amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Автоматично оновлюється при додаванні транзакцій
    spent_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")

    # Зв'язки
    user: Mapped["User"] = relationship("User", back_populates="budgets")
    category: Mapped["Category"] = relationship("Category", back_populates="budgets")

    @property
    def remaining(self) -> float:
        return self.limit_amount - self.spent_amount

    @property
    def is_exceeded(self) -> bool:
        return self.spent_amount > self.limit_amount

    def __repr__(self) -> str:
        return (
            f"<Budget id={self.id} month={self.month} "
            f"spent={self.spent_amount}/{self.limit_amount} {self.currency}>"
        )
