from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import Account, Transaction, Transfer, Budget
from app.services.exchange_rate_service import exchange_rate_service


TYPE_EMOJI = {"expense": "➖", "income": "➕", "transfer": "🔄", "debt_payment": "💳"}
_NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def build_multi_confirmation_text(multi_txs: list) -> str:
    lines = ["📋 <b>Підтвердіть транзакції:</b>"]
    for i, d in enumerate(multi_txs):
        num = _NUM_EMOJI[i] if i < len(_NUM_EMOJI) else f"{i + 1}."
        tx_type = d.get("tx_type", "expense")
        amount = d.get("amount", 0)
        currency = d.get("currency", "UAH")
        description = d.get("description") or "—"
        account_name = d.get("account_name", "—")
        cat_name = d.get("category_name") or "Інше"
        emoji = TYPE_EMOJI.get(tx_type, "💸")
        lines.append(f"\n{num}")
        lines.append(f"— Тип: {emoji} <b>{tx_type}</b>")
        lines.append(f"💰 Сума: <b>{amount} {currency}</b>")
        lines.append(f"📝 Опис: {description}")
        lines.append(f"🏦 Рахунок: {account_name}")
        lines.append(f"🏷 Категорія: {cat_name}")
    return "\n".join(lines)


def build_confirmation_text(d: dict) -> str:
    parsed = d["parsed"]
    tx_type = d.get("tx_type") or parsed.get("type", "expense")
    amount = d.get("amount") or parsed.get("amount", 0)
    currency = d.get("currency") or parsed.get("currency", "UAH")
    description = d.get("description") or parsed.get("description") or "—"
    account_name = d.get("account_name", "—")
    is_new_cat = d.get("is_new_cat", False)
    cat_display = (
        f"🆕 {d.get('new_cat_name', '?')} <i>(нова — буде створена)</i>"
        if is_new_cat
        else d.get("category_name", "Без категорії")
    )
    emoji = TYPE_EMOJI.get(tx_type, "💸")
    return (
        f"📋 <b>Підтвердіть транзакцію:</b>\n\n"
        f"{emoji} Тип: <b>{tx_type}</b>\n"
        f"💵 Сума: <b>{amount} {currency}</b>\n"
        f"📝 Опис: {description}\n"
        f"🏦 Рахунок: {account_name}\n"
        f"🏷 Категорія: {cat_display}"
    )


async def load_recent_activity(user_id: int, limit: int = 10) -> list:
    """Завантажує останні транзакції і перекази, об'єднані та відсортовані за датою.

    Повертає список об'єктів з полями kind ('tx' | 'transfer'), id, type,
    amount, currency, description, date — спільними для уніфікованого списку.
    """
    async with AsyncSessionLocal() as db:
        tx_res = await db.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.date.desc())
            .limit(limit)
        )
        transactions = tx_res.scalars().all()

        tr_res = await db.execute(
            select(Transfer)
            .where(Transfer.user_id == user_id)
            .order_by(Transfer.date.desc())
            .limit(limit)
        )
        transfers = tr_res.scalars().all()

        acc_ids = {t.from_account_id for t in transfers} | {t.to_account_id for t in transfers}
        accounts: dict[int, Account] = {}
        if acc_ids:
            acc_res = await db.execute(select(Account).where(Account.id.in_(acc_ids)))
            accounts = {a.id: a for a in acc_res.scalars().all()}

    items = [
        SimpleNamespace(
            kind="tx", id=tx.id, type=tx.type, amount=tx.amount,
            currency=tx.currency, description=tx.description, date=tx.date,
        )
        for tx in transactions
    ]
    for tr in transfers:
        from_acc = accounts.get(tr.from_account_id)
        to_acc = accounts.get(tr.to_account_id)
        desc = f"{from_acc.name if from_acc else '?'} → {to_acc.name if to_acc else '?'}"
        items.append(SimpleNamespace(
            kind="transfer", id=tr.id, type="transfer", amount=tr.amount,
            currency=tr.currency, description=desc, date=tr.date,
        ))

    items.sort(key=lambda x: x.date, reverse=True)
    return items[:limit]


async def save_transaction(user_id: int, d: dict) -> Transaction:
    """Зберігає транзакцію, оновлює баланс рахунку і витрати бюджету."""
    parsed = d["parsed"]
    tx_type = d.get("tx_type") or parsed.get("type", "expense")
    amount = float(d.get("amount") or parsed.get("amount", 0))
    currency = d.get("currency") or parsed.get("currency", "UAH")
    description = d.get("description") or parsed.get("description")
    amount_uah = await exchange_rate_service.to_uah(amount, currency)

    async with AsyncSessionLocal() as db:
        tx = Transaction(
            user_id=user_id,
            account_id=d["account_id"],
            category_id=d.get("category_id"),
            type=tx_type,
            amount=amount,
            currency=currency,
            amount_uah=amount_uah,
            description=description,
            date=datetime.utcnow(),
            source=d.get("source", "bot_text"),
            external_id=d.get("external_id"),
        )
        db.add(tx)

        # Оновлення балансу
        acc = await db.get(Account, d["account_id"])
        if acc:
            if tx_type == "income":
                acc.balance += amount
            elif tx_type in ("expense", "debt_payment"):
                acc.balance -= amount

        # Оновлення бюджету при витраті
        if tx_type == "expense" and d.get("category_id"):
            month_str = datetime.utcnow().strftime("%Y-%m")
            res = await db.execute(
                select(Budget).where(
                    and_(
                        Budget.user_id == user_id,
                        Budget.category_id == d["category_id"],
                        Budget.month == month_str,
                    )
                )
            )
            budget = res.scalar_one_or_none()
            if budget:
                budget.spent_amount += amount_uah

        await db.commit()
        await db.refresh(tx)
        return tx
