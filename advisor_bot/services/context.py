from datetime import datetime, timedelta

from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import Account, Transaction, Debt, Goal, Subscription, Budget, Category

TX_SIGN = {"income": "➕", "expense": "➖", "debt_payment": "💳", "transfer": "🔄"}
RECENT_TX_LIMIT = 15


async def build_user_context(user_id: int) -> str:
    """Збирає текстовий зріз фінансового стану юзера для системного промпту Claude."""
    since = datetime.utcnow() - timedelta(days=30)
    month_str = datetime.utcnow().strftime("%Y-%m")

    async with AsyncSessionLocal() as db:
        accounts = (
            await db.execute(select(Account).where(Account.user_id == user_id))
        ).scalars().all()

        transactions = (
            await db.execute(
                select(Transaction)
                .where(and_(Transaction.user_id == user_id, Transaction.date >= since))
                .order_by(Transaction.date.desc())
            )
        ).scalars().all()

        debts = (
            await db.execute(select(Debt).where(Debt.user_id == user_id))
        ).scalars().all()

        goals = (
            await db.execute(select(Goal).where(Goal.user_id == user_id))
        ).scalars().all()

        subscriptions = (
            await db.execute(
                select(Subscription).where(
                    and_(Subscription.user_id == user_id, Subscription.is_active.is_(True))
                )
            )
        ).scalars().all()

        budget_rows = (
            await db.execute(
                select(Budget, Category)
                .join(Category, Budget.category_id == Category.id)
                .where(and_(Budget.user_id == user_id, Budget.month == month_str))
            )
        ).all()

    lines: list[str] = []

    lines.append("РАХУНКИ:")
    if accounts:
        for acc in accounts:
            lines.append(f"- {acc.name}: {acc.balance:.2f} {acc.currency}")
    else:
        lines.append("- немає рахунків")

    lines.append("")
    lines.append("ТРАНЗАКЦІЇ за останні 30 днів:")
    if transactions:
        income = sum(t.amount_uah for t in transactions if t.type == "income")
        expense = sum(t.amount_uah for t in transactions if t.type in ("expense", "debt_payment"))
        lines.append(f"- Кількість: {len(transactions)}, доходи: {income:.0f} ₴, витрати: {expense:.0f} ₴, різниця: {income - expense:+.0f} ₴")
        lines.append("- Останні операції:")
        for t in transactions[:RECENT_TX_LIMIT]:
            sign = TX_SIGN.get(t.type, "")
            desc = t.description or "—"
            lines.append(f"  {t.date.strftime('%d.%m')} {sign} {t.amount:.0f} {t.currency} — {desc}")
    else:
        lines.append("- транзакцій не було")

    lines.append("")
    lines.append("БОРГИ:")
    if debts:
        for d in debts:
            lines.append(
                f"- {d.name}: залишок {d.remaining_amount:.0f} {d.currency}, "
                f"платіж/міс {d.monthly_payment:.0f} {d.currency}"
            )
    else:
        lines.append("- немає боргів")

    lines.append("")
    lines.append("ЦІЛІ:")
    if goals:
        for g in goals:
            lines.append(
                f"- {g.name}: {g.current_amount:.0f}/{g.target_amount:.0f} {g.currency} "
                f"({g.progress_percent:.0f}%)"
            )
    else:
        lines.append("- немає цілей")

    lines.append("")
    lines.append("ПІДПИСКИ (активні):")
    if subscriptions:
        for s in subscriptions:
            period = "міс." if s.period == "monthly" else "рік"
            lines.append(f"- {s.name}: {s.amount:.0f} {s.currency} / {period}")
    else:
        lines.append("- немає активних підписок")

    lines.append("")
    lines.append(f"БЮДЖЕТИ ({month_str}):")
    if budget_rows:
        for budget, category in budget_rows:
            lines.append(
                f"- {category.name}: витрачено {budget.spent_amount:.0f}/{budget.limit_amount:.0f} {budget.currency}"
            )
    else:
        lines.append("- бюджетів не встановлено")

    return "\n".join(lines)
