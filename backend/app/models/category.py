from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # expense або income
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="expense")
    # Емодзі або назва іконки
    icon: Mapped[str | None] = mapped_column(String(64), nullable=True, default="💰")
    # HEX-колір для UI
    color: Mapped[str | None] = mapped_column(String(16), nullable=True, default="#5557f5")

    # Зв'язки
    user: Mapped["User"] = relationship("User", back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="category")
    budgets: Mapped[list["Budget"]] = relationship("Budget", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} type={self.type}>"
