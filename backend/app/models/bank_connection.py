from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class BankConnection(Base):
    """Підключення банку до користувача (наразі — Monobank).

    Зберігає ТІЛЬКИ зашифрований токен (Fernet, ключ TOKEN_ENCRYPTION_KEY).
    Токен ніколи не логується і не зберігається у відкритому вигляді.
    """
    __tablename__ = "bank_connections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="monobank")
    encrypted_token: Mapped[str] = mapped_column(String(512), nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    # Зв'язки. Видалення з'єднання каскадно прибирає картки (bank_cards),
    # але НЕ рахунки та транзакції — вони живуть окремо.
    user: Mapped["User"] = relationship("User", back_populates="bank_connections")
    cards: Mapped[list["BankCard"]] = relationship(
        "BankCard", back_populates="connection", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BankConnection id={self.id} user_id={self.user_id} provider={self.provider}>"
