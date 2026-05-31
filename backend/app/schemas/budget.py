from pydantic import BaseModel, Field
from typing import Optional
import re


class BudgetBase(BaseModel):
    category_id: int
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    limit_amount: float = Field(..., gt=0)
    currency: str = Field(default="UAH")


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    limit_amount: Optional[float] = Field(None, gt=0)


class BudgetResponse(BudgetBase):
    id: int
    user_id: int
    spent_amount: float
    remaining: float
    is_exceeded: bool

    model_config = {"from_attributes": True}
