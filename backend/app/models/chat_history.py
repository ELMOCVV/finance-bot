from datetime import datetime
from sqlalchemy import String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Розділяє історію різних ботів (напр. 'main', 'advisor')
    bot_type: Mapped[str] = mapped_column(String(32), nullable=False, default="main", index=True)
    # user | assistant
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False, index=True)

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ChatHistory id={self.id} user_id={self.user_id} bot_type={self.bot_type} role={self.role}>"
