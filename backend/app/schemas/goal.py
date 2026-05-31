from datetime import date, datetime
from pydantic import BaseModel, Field
from typing import Optional


class GoalBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    target_amount: float = Field(..., gt=0)
    current_amount: float = Field(default=0.0, ge=0)
    currency: str = Field(default="UAH")
    deadline: Optional[date] = None


class GoalCreate(GoalBase):
    pass


class GoalUpdate(BaseModel):
    current_amount: Optional[float] = Field(None, ge=0)
    target_amount: Optional[float] = Field(None, gt=0)
    deadline: Optional[date] = None


class GoalResponse(GoalBase):
    id: int
    user_id: int
    progress_percent: float
    created_at: datetime

    model_config = {"from_attributes": True}
