from typing import Optional
from pydantic import BaseModel, field_validator


class WalletTxIn(BaseModel):
    """Тіло запиту від iOS «Команд» (Wallet-тригер). Усі поля — рядки."""
    amount: str
    merchant: Optional[str] = None
    card: Optional[str] = None

    @field_validator("amount", mode="before")
    @classmethod
    def amount_to_str(cls, v):
        # «Команди» інколи шлють число замість тексту
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v

    @field_validator("merchant", "card", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class WalletTxOut(BaseModel):
    ok: bool = True
    id: int
