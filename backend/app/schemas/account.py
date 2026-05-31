from pydantic import BaseModel, Field
from typing import Optional


class AccountBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    currency: str = Field(default="UAH", pattern=r"^[A-Z]{2,10}$")
    keywords: Optional[list[str]] = Field(default_factory=list)
    is_default: bool = False


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    currency: Optional[str] = None
    balance: Optional[float] = None
    keywords: Optional[list[str]] = None
    is_default: Optional[bool] = None


class AccountResponse(AccountBase):
    id: int
    user_id: int
    balance: float

    model_config = {"from_attributes": True}
