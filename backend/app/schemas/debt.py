from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional


class DebtBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    total_amount: float = Field(..., gt=0)
    remaining_amount: float = Field(..., ge=0)
    monthly_payment: float = Field(default=0.0, ge=0)
    interest_rate: float = Field(default=0.0, ge=0)
    next_payment_date: Optional[date] = None
    currency: str = Field(default="UAH")


class DebtCreate(DebtBase):
    pass


class DebtUpdate(BaseModel):
    remaining_amount: Optional[float] = Field(None, ge=0)
    monthly_payment: Optional[float] = Field(None, ge=0)
    next_payment_date: Optional[date] = None


class DebtResponse(DebtBase):
    id: int
    user_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
