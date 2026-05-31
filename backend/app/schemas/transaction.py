from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Literal


class TransactionBase(BaseModel):
    account_id: int
    category_id: Optional[int] = None
    type: Literal["expense", "income", "debt_payment", "transfer"]
    amount: float = Field(..., gt=0)
    currency: str = Field(default="UAH")
    description: Optional[str] = Field(None, max_length=512)
    date: Optional[datetime] = None
    source: Literal["manual", "bot_text", "bot_photo"] = "manual"


class TransactionCreate(TransactionBase):
    pass


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    date: Optional[datetime] = None


class TransactionResponse(TransactionBase):
    id: int
    user_id: int
    amount_uah: float
    date: datetime

    model_config = {"from_attributes": True}
