from datetime import datetime, date
from typing import Optional
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Transaction, Account, Category, Budget, Goal, Debt


class AnalyticsService:

    async def get_summary(self, db: AsyncSession, user_id: int, month: str) -> dict:
        """Зведення за місяць: доходи, витрати, баланс по рахунках."""
        year, mon = map(int, month.split("-"))
        start = datetime(year, mon, 1)
        end = datetime(year, mon + 1, 1) if mon < 12 else datetime(year + 1, 1, 1)

        # Загальні доходи за місяць (в UAH)
        income_q = await db.execute(
            select(func.sum(Transaction.amount_uah)).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.type == "income",
                    Transaction.date >= start,
                    Transaction.date < end,
                )
            )
        )
        total_income = income_q.scalar() or 0.0

        # Загальні витрати за місяць
        expense_q = await db.execute(
            select(func.sum(Transaction.amount_uah)).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.type == "expense",
                    Transaction.date >= start,
                    Transaction.date < end,
                )
            )
        )
        total_expense = expense_q.scalar() or 0.0

        # Баланс по рахунках
        accounts_q = await db.execute(
            select(Account).where(Account.user_id == user_id)
        )
        accounts = accounts_q.scalars().all()

        return {
            "month": month,
            "total_income_uah": round(total_income, 2),
            "total_expense_uah": round(total_expense, 2),
            "net_uah": round(total_income - total_expense, 2),
            "accounts": [
                {"id": a.id, "name": a.name, "balance": a.balance, "currency": a.currency}
                for a in accounts
            ],
        }

    async def get_expenses_by_category(
        self, db: AsyncSession, user_id: int, month: str
    ) -> list[dict]:
        """Розподіл витрат по категоріях за місяць."""
        year, mon = map(int, month.split("-"))
        start = datetime(year, mon, 1)
        end = datetime(year, mon + 1, 1) if mon < 12 else datetime(year + 1, 1, 1)

        result = await db.execute(
            select(
                Category.id,
                Category.name,
                Category.icon,
                Category.color,
                func.sum(Transaction.amount_uah).label("total"),
            )
            .join(Transaction, Transaction.category_id == Category.id)
            .where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.type == "expense",
                    Transaction.date >= start,
                    Transaction.date < end,
                )
            )
            .group_by(Category.id)
            .order_by(func.sum(Transaction.amount_uah).desc())
        )
        rows = result.all()
        return [
            {
                "category_id": r.id,
                "name": r.name,
                "icon": r.icon,
                "color": r.color,
                "total_uah": round(r.total, 2),
            }
            for r in rows
        ]

    async def get_monthly_trend(
        self, db: AsyncSession, user_id: int, months: int = 6
    ) -> list[dict]:
        """Тренд доходів/витрат за останні N місяців."""
        result = await db.execute(
            select(
                func.strftime("%Y-%m", Transaction.date).label("month"),
                Transaction.type,
                func.sum(Transaction.amount_uah).label("total"),
            )
            .where(Transaction.user_id == user_id)
            .group_by(func.strftime("%Y-%m", Transaction.date), Transaction.type)
            .order_by(func.strftime("%Y-%m", Transaction.date).desc())
        )
        rows = result.all()

        # Агрегуємо по місяцях
        trend: dict[str, dict] = {}
        for row in rows:
            m = row.month
            if m not in trend:
                trend[m] = {"month": m, "income": 0.0, "expense": 0.0}
            if row.type == "income":
                trend[m]["income"] = round(row.total, 2)
            elif row.type == "expense":
                trend[m]["expense"] = round(row.total, 2)

        return sorted(trend.values(), key=lambda x: x["month"])[-months:]

    async def get_budget_status(self, db: AsyncSession, user_id: int, month: str) -> list[dict]:
        """Статус бюджетів за місяць."""
        result = await db.execute(
            select(Budget, Category.name, Category.icon)
            .join(Category, Budget.category_id == Category.id)
            .where(and_(Budget.user_id == user_id, Budget.month == month))
        )
        rows = result.all()
        return [
            {
                "budget_id": b.id,
                "category": name,
                "icon": icon,
                "limit": b.limit_amount,
                "spent": b.spent_amount,
                "remaining": b.remaining,
                "is_exceeded": b.is_exceeded,
                "currency": b.currency,
            }
            for b, name, icon in rows
        ]


analytics_service = AnalyticsService()
