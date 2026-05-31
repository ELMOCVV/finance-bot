from datetime import datetime, date
from sqlalchemy import String, Float, ForeignKey, DateTime, Date, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    target_amount: Mapped[float] = mapped_column(Float, nullable=False)
    current_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Зв'язок
    user: Mapped["User"] = relationship("User", back_populates="goals")

    @property
    def progress_percent(self) -> float:
        """Відсоток виконання цілі."""
        if self.target_amount == 0:
            return 0.0
        return round(self.current_amount / self.target_amount * 100, 1)

    def __repr__(self) -> str:
        return (
            f"<Goal id={self.id} name={self.name!r} "
            f"{self.current_amount}/{self.target_amount} {self.currency}>"
        )
