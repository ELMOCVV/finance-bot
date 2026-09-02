from pydantic import BaseModel, Field


class ResetSummaryResponse(BaseModel):
    """Підсумок скидання даних: скільки рядків видалено і скільки
    рахунків обнулено."""

    transactions: int = Field(..., description="Видалено транзакцій")
    transfers: int = Field(..., description="Видалено переказів")
    goals: int = Field(..., description="Видалено цілей")
    debts: int = Field(..., description="Видалено боргів")
    budgets: int = Field(..., description="Видалено бюджетів")
    bank_connections: int = Field(..., description="Видалено банківських підключень")
    accounts_reset: int = Field(..., description="Рахунків з обнуленим балансом")
