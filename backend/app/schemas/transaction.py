from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Literal


# ── Create (строга валідація для вхідних даних) ───────────────────────────────

class TransactionCreate(BaseModel):
    account_id: int
    category_id: Optional[int] = None
    type: Literal["expense", "income", "debt_payment", "transfer"]
    amount: float = Field(..., gt=0)
    currency: str = Field(default="UAH")
    description: Optional[str] = Field(None, max_length=512)
    date: Optional[datetime] = None
    source: Literal["manual", "bot_text", "bot_photo"] = "manual"


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    date: Optional[datetime] = None


# ── Response (м'яка валідація — дані можуть містити legacy-значення з БД) ────

class TransactionResponse(BaseModel):
    """Response schema: не використовує Literal/gt щоб не падати на legacy-даних."""
    id: int
    user_id: int
    account_id: int
    category_id: Optional[int] = None
    type: str
    amount: float
    currency: str = "UAH"
    amount_uah: float = 0.0
    description: Optional[str] = None
    date: datetime
    source: str = "manual"

    model_config = {"from_attributes": True}
