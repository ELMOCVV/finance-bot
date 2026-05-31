from pydantic import BaseModel, Field
from typing import Optional, Literal


class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: Literal["expense", "income"] = "expense"
    icon: Optional[str] = "💰"
    color: Optional[str] = "#5557f5"


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: int
    user_id: int

    model_config = {"from_attributes": True}
