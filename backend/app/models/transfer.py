from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    from_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    to_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="UAH")
    amount_uah: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    # Зв'язки
    user: Mapped["User"] = relationship("User", back_populates="transfers")
    from_account: Mapped["Account"] = relationship(
        "Account", foreign_keys=[from_account_id], back_populates="transfers_from"
    )
    to_account: Mapped["Account"] = relationship(
        "Account", foreign_keys=[to_account_id], back_populates="transfers_to"
    )

    def __repr__(self) -> str:
        return (
            f"<Transfer id={self.id} from={self.from_account_id} "
            f"to={self.to_account_id} amount={self.amount} {self.currency}>"
        )
