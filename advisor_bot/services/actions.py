"""Дії Money Deck Advisor через Claude tool-use.

Claude обирає інструмент → тут ми його ГОТУЄМО (резолвимо назви у сутності,
будуємо текст-підтвердження та HTTP-виклик), але НЕ виконуємо одразу. Реальне
виконання відбувається лише після кнопки «✅ Так» (див. handlers/chat.py) —
через бекенд-API, тож усі транзакції отримують source="advisor_action" і
потім видно в аналітиці, що це зробив бот, а не юзер вручну.

Резолвинг назв — читання з БД (той самий зріз, що бачить Claude у контексті).
Мутації — через HTTP до BACKEND_URL, щоб спрацювала серверна логіка роутерів.
"""
import logging
from datetime import datetime, date

import httpx
from sqlalchemy import select, and_

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Account, Goal, Debt, Category, Budget

logger = logging.getLogger(__name__)

_MONTHS_UA_GEN = [
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]


# ── Опис інструментів для Claude ──────────────────────────────────────────────

TOOLS = [
    {
        "name": "adjust_account_balance",
        "description": (
            "Виставити рахунку новий фактичний баланс (коригування). Різниця "
            "фіксується транзакцією. Використовуй лише коли відома конкретна "
            "назва рахунку та нове числове значення балансу."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_name": {"type": "string", "description": "Назва рахунку як у контексті користувача"},
                "new_balance": {"type": "number", "description": "Новий баланс, не менше 0"},
            },
            "required": ["account_name", "new_balance"],
        },
    },
    {
        "name": "create_goal",
        "description": "Створити нову фінансову ціль. Потрібні назва і цільова сума.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "target_amount": {"type": "number", "description": "Цільова сума, більше 0"},
                "currency": {"type": "string", "description": "Валюта, напр. UAH"},
                "deadline": {"type": "string", "description": "Дедлайн у форматі YYYY-MM-DD або null"},
            },
            "required": ["name", "target_amount", "currency"],
        },
    },
    {
        "name": "update_goal",
        "description": "Оновити наявну ціль: цільову суму, накопичену суму та/або дедлайн.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_name": {"type": "string", "description": "Назва наявної цілі"},
                "target_amount": {"type": "number"},
                "current_amount": {"type": "number"},
                "deadline": {"type": "string", "description": "YYYY-MM-DD або null"},
            },
            "required": ["goal_name"],
        },
    },
    {
        "name": "update_budget_limit",
        "description": "Змінити ліміт бюджету для категорії у поточному місяці.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category_name": {"type": "string"},
                "limit_amount": {"type": "number", "description": "Новий ліміт, більше 0"},
            },
            "required": ["category_name", "limit_amount"],
        },
    },
    {
        "name": "create_debt",
        "description": "Створити запис про борг/кредит.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "total_amount": {"type": "number", "description": "Загальна сума боргу, більше 0"},
                "monthly_payment": {"type": "number", "description": "Щомісячний платіж"},
                "currency": {"type": "string"},
                "interest_rate": {"type": "number", "description": "Річна ставка %, або null"},
                "next_payment_date": {"type": "string", "description": "YYYY-MM-DD або null"},
            },
            "required": ["name", "total_amount", "monthly_payment", "currency"],
        },
    },
    {
        "name": "add_debt_payment",
        "description": "Внести платіж по наявному боргу з конкретного рахунку.",
        "input_schema": {
            "type": "object",
            "properties": {
                "debt_name": {"type": "string"},
                "account_name": {"type": "string"},
                "amount": {"type": "number", "description": "Сума платежу, більше 0"},
            },
            "required": ["debt_name", "account_name", "amount"],
        },
    },
]


# ── Форматування ──────────────────────────────────────────────────────────────

def _money(amount: float, currency: str = "UAH") -> str:
    body = f"{amount:,.0f}".replace(",", " ")
    if currency.upper() == "UAH":
        return f"{body}₴"
    return f"{body} {currency}"


def _fmt_deadline(value: str | date | None) -> str:
    if not value:
        return "без терміну"
    try:
        d = value if isinstance(value, date) else datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        return f"до {d.day} {_MONTHS_UA_GEN[d.month - 1]} {d.year}"
    except Exception:
        return str(value)


# ── Резолвинг назв у сутності (read-only з БД) ────────────────────────────────

def _best_match(name: str, items: list, attr: str = "name"):
    if not name:
        return None
    n = name.strip().lower()
    for it in items:  # точний збіг
        if getattr(it, attr).strip().lower() == n:
            return it
    for it in items:  # підрядок
        v = getattr(it, attr).strip().lower()
        if n in v or v in n:
            return it
    return None


async def _resolve_account(user_id: int, name: str) -> Account | None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Account).where(Account.user_id == user_id))).scalars().all()
    return _best_match(name, rows)


async def _resolve_goal(user_id: int, name: str) -> Goal | None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Goal).where(Goal.user_id == user_id))).scalars().all()
    return _best_match(name, rows)


async def _resolve_debt(user_id: int, name: str) -> Debt | None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(Debt).where(Debt.user_id == user_id))).scalars().all()
    return _best_match(name, rows)


async def _resolve_budget(user_id: int, category_name: str, month: str):
    """Повертає (Budget, Category) для категорії у вказаному місяці або (None, cat/None)."""
    async with AsyncSessionLocal() as db:
        cats = (await db.execute(select(Category).where(Category.user_id == user_id))).scalars().all()
        cat = _best_match(category_name, cats)
        if not cat:
            return None, None
        budget = (await db.execute(
            select(Budget).where(and_(
                Budget.user_id == user_id,
                Budget.category_id == cat.id,
                Budget.month == month,
            ))
        )).scalar_one_or_none()
    return budget, cat


# ── Підготовка дії: (prepared | None, error | None) ───────────────────────────

async def prepare(user_id: int, tool: str, args: dict) -> tuple[dict | None, str | None]:
    """Резолвить дію і будує текст-підтвердження + HTTP-виклик.

    Повертає (prepared, None) при успіху або (None, повідомлення-помилка).
    prepared: {tool, method, path, payload, confirm_text, meta}
    """
    try:
        if tool == "adjust_account_balance":
            acc = await _resolve_account(user_id, args["account_name"])
            if not acc:
                return None, f"Не знайшов рахунок «{args['account_name']}». Уточни, будь ласка."
            new_balance = float(args["new_balance"])
            if new_balance < 0:
                return None, "Баланс не може бути від'ємним."
            delta = new_balance - acc.balance
            delta_str = ("+" if delta >= 0 else "−") + _money(abs(delta), acc.currency)
            confirm = (
                f"💰 Скоригувати баланс «{acc.name}»?\n"
                f"Було: {_money(acc.balance, acc.currency)} · "
                f"Стане: {_money(new_balance, acc.currency)} ({delta_str})"
            )
            return {
                "tool": tool, "method": "POST",
                "path": f"/api/v1/accounts/{acc.id}/adjust-balance",
                "payload": {"new_balance": new_balance},
                "confirm_text": confirm,
                "meta": {"account": acc.name, "currency": acc.currency, "new_balance": new_balance},
            }, None

        if tool == "create_goal":
            target = float(args["target_amount"])
            if target <= 0:
                return None, "Цільова сума має бути більше 0."
            currency = args.get("currency") or "UAH"
            deadline = args.get("deadline") or None
            confirm = (
                f"🎯 Створити ціль «{args['name']}»?\n"
                f"Сума: {_money(target, currency)} · Термін: {_fmt_deadline(deadline)}"
            )
            payload = {"name": args["name"], "target_amount": target, "currency": currency}
            if deadline:
                payload["deadline"] = str(deadline)[:10]
            return {
                "tool": tool, "method": "POST", "path": "/api/v1/goals/",
                "payload": payload, "confirm_text": confirm,
                "meta": {"name": args["name"], "target": target, "currency": currency},
            }, None

        if tool == "update_goal":
            goal = await _resolve_goal(user_id, args["goal_name"])
            if not goal:
                return None, f"Не знайшов ціль «{args['goal_name']}»."
            payload, changes = {}, []
            if args.get("target_amount") is not None:
                payload["target_amount"] = float(args["target_amount"])
                changes.append(f"Мета: {_money(payload['target_amount'], goal.currency)}")
            if args.get("current_amount") is not None:
                payload["current_amount"] = float(args["current_amount"])
                changes.append(f"Накопичено: {_money(payload['current_amount'], goal.currency)}")
            if args.get("deadline"):
                payload["deadline"] = str(args["deadline"])[:10]
                changes.append(f"Термін: {_fmt_deadline(args['deadline'])}")
            if not payload:
                return None, "Не вказано, що саме оновити в цілі."
            confirm = f"✏️ Оновити ціль «{goal.name}»?\n" + " · ".join(changes)
            return {
                "tool": tool, "method": "PATCH", "path": f"/api/v1/goals/{goal.id}",
                "payload": payload, "confirm_text": confirm,
                "meta": {"name": goal.name},
            }, None

        if tool == "update_budget_limit":
            month = datetime.utcnow().strftime("%Y-%m")
            budget, cat = await _resolve_budget(user_id, args["category_name"], month)
            if not cat:
                return None, f"Не знайшов категорію «{args['category_name']}»."
            if not budget:
                return None, f"На цей місяць немає бюджету для «{cat.name}» — спершу створи його в застосунку."
            limit = float(args["limit_amount"])
            if limit <= 0:
                return None, "Ліміт має бути більше 0."
            confirm = (
                f"📋 Змінити ліміт бюджету «{cat.name}»?\n"
                f"Було: {_money(budget.limit_amount, budget.currency)} · "
                f"Стане: {_money(limit, budget.currency)}"
            )
            return {
                "tool": tool, "method": "PATCH", "path": f"/api/v1/budgets/{budget.id}",
                "payload": {"limit_amount": limit}, "confirm_text": confirm,
                "meta": {"category": cat.name, "limit": limit, "currency": budget.currency},
            }, None

        if tool == "create_debt":
            total = float(args["total_amount"])
            if total <= 0:
                return None, "Сума боргу має бути більше 0."
            currency = args.get("currency") or "UAH"
            monthly = float(args.get("monthly_payment") or 0)
            payload = {
                "name": args["name"], "total_amount": total,
                "remaining_amount": total, "monthly_payment": monthly,
                "currency": currency,
            }
            extra = []
            if args.get("interest_rate") is not None:
                payload["interest_rate"] = float(args["interest_rate"])
                extra.append(f"ставка {payload['interest_rate']:g}%")
            if args.get("next_payment_date"):
                payload["next_payment_date"] = str(args["next_payment_date"])[:10]
                extra.append(_fmt_deadline(args["next_payment_date"]))
            confirm = (
                f"💳 Створити борг «{args['name']}»?\n"
                f"Сума: {_money(total, currency)} · Платіж/міс: {_money(monthly, currency)}"
                + (f"\n" + " · ".join(extra) if extra else "")
            )
            return {
                "tool": tool, "method": "POST", "path": "/api/v1/debts/",
                "payload": payload, "confirm_text": confirm,
                "meta": {"name": args["name"], "currency": currency},
            }, None

        if tool == "add_debt_payment":
            debt = await _resolve_debt(user_id, args["debt_name"])
            if not debt:
                return None, f"Не знайшов борг «{args['debt_name']}»."
            acc = await _resolve_account(user_id, args["account_name"])
            if not acc:
                return None, f"Не знайшов рахунок «{args['account_name']}»."
            amount = float(args["amount"])
            if amount <= 0:
                return None, "Сума платежу має бути більше 0."
            new_remaining = max(0.0, debt.remaining_amount - amount)
            new_balance = acc.balance - amount
            confirm = (
                f"💳 Платіж по боргу «{debt.name}»?\n"
                f"З рахунку «{acc.name}» · Сума: {_money(amount, acc.currency)}\n"
                f"Залишок боргу стане: {_money(new_remaining, debt.currency)} · "
                f"Баланс рахунку: {_money(new_balance, acc.currency)}"
            )
            return {
                "tool": tool, "method": "POST", "path": f"/api/v1/debts/{debt.id}/payment",
                "payload": {"account_id": acc.id, "amount": amount},
                "confirm_text": confirm,
                "meta": {"debt": debt.name, "account": acc.name, "amount": amount, "currency": acc.currency},
            }, None

        return None, "Невідома дія."
    except (KeyError, TypeError, ValueError) as e:
        logger.warning("prepare(%s) error: %s", tool, e)
        return None, "Бракує даних для цієї дії — уточни, будь ласка, суми та назви."


# ── Виконання підтвердженої дії через API ─────────────────────────────────────

async def execute(user_id: int, prepared: dict) -> tuple[str | None, str | None]:
    """Виконує prepared-дію через бекенд-API. Повертає (success_text, error)."""
    url = settings.BACKEND_URL.rstrip("/") + prepared["path"]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                prepared["method"], url,
                params={"user_id": user_id}, json=prepared["payload"],
            )
        if resp.status_code >= 400:
            logger.warning("Advisor action %s failed: %s %s", prepared["tool"], resp.status_code, resp.text[:200])
            return None, "Не вдалося виконати дію — спробуй трохи пізніше."
        data = resp.json() if resp.content else {}
    except Exception as e:
        logger.error("Advisor action %s exception: %s", prepared["tool"], e)
        return None, "Не вдалося звʼязатися з сервером. Спробуй пізніше."
    return _build_success(prepared, data), None


def _build_success(prepared: dict, data: dict) -> str:
    tool, m = prepared["tool"], prepared["meta"]
    if tool == "adjust_account_balance":
        bal = data.get("balance", m["new_balance"])
        return f"✅ Готово! Баланс «{m['account']}» тепер {_money(bal, m['currency'])}."
    if tool == "create_goal":
        return f"✅ Ціль «{m['name']}» створено. Мета: {_money(m['target'], m['currency'])}."
    if tool == "update_goal":
        return f"✅ Ціль «{m['name']}» оновлено."
    if tool == "update_budget_limit":
        return f"✅ Ліміт бюджету «{m['category']}» тепер {_money(m['limit'], m['currency'])}."
    if tool == "create_debt":
        return f"✅ Борг «{m['name']}» додано."
    if tool == "add_debt_payment":
        remaining = data.get("remaining_amount")
        tail = f" Залишок боргу: {_money(remaining, m['currency'])}." if remaining is not None else ""
        return f"✅ Платіж {_money(m['amount'], m['currency'])} по «{m['debt']}» зараховано.{tail}"
    return "✅ Готово!"
