"""Apple Wallet (iOS «Команди») → витрата.

Парсинг суми з текстом валюти, підбір категорії за словником ключових слів
(app/services/wallet_category_keywords.py), вибір рахунку та дедуплікація.
Сам запис транзакції — через спільний create_transaction_record.
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Category, Transaction
from app.services.wallet_category_keywords import CATEGORY_RULES, FALLBACK_CATEGORY_NAMES

WALLET_SOURCE = "wallet"
DEDUP_WINDOW = timedelta(seconds=60)

# Символ / код валюти → ISO-код. Порядок важливий лише для довших збігів.
_CURRENCY_MARKERS: list[tuple[str, str]] = [
    ("₴", "UAH"), ("грн", "UAH"), ("uah", "UAH"),
    ("€", "EUR"), ("eur", "EUR"),
    ("$", "USD"), ("usd", "USD"),
]
DEFAULT_CURRENCY = "UAH"

# Усі види пробілів, якими iOS розділяє тисячі (звичайний, NBSP, вузький NBSP, thin space)
_SPACES_RE = re.compile(r"[\s    ]+")
_NUMBER_RE = re.compile(r"\d[\d.,]*")


def parse_wallet_amount(raw: str) -> tuple[Decimal, str]:
    """"1 250,50 ₴" → (Decimal("1250.50"), "UAH").

    Підтримує символи ₴/€/$ (і коди UAH/EUR/USD/грн) до або після числа,
    кому чи крапку як десятковий роздільник, пробіли/NBSP/крапку/кому як
    роздільник тисяч. Валюта за замовчуванням — UAH.
    Кидає ValueError, якщо суму розібрати не вдалося або вона не додатна.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("empty amount")

    text = raw.strip().lower()
    currency = next((code for marker, code in _CURRENCY_MARKERS if marker in text), DEFAULT_CURRENCY)

    numbers = _NUMBER_RE.findall(_SPACES_RE.sub("", text))
    if len(numbers) != 1:
        raise ValueError(f"cannot find a single number in {raw!r}")
    number = numbers[0].rstrip(".,")

    last_dot, last_comma = number.rfind("."), number.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        # Обидва роздільники: десятковий — той, що правіше
        decimal_sep = "." if last_dot > last_comma else ","
        thousands_sep = "," if decimal_sep == "." else "."
        number = number.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif last_dot >= 0 or last_comma >= 0:
        sep = "." if last_dot >= 0 else ","
        parts = number.split(sep)
        # "1.250" / "1,250,000" — роздільник тисяч; "250,00" / "5.5" — десятковий
        if len(parts) > 2 or len(parts[-1]) == 3:
            number = "".join(parts)
        else:
            number = ".".join(parts)

    try:
        amount = Decimal(number)
    except InvalidOperation:
        raise ValueError(f"invalid number in {raw!r}") from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"amount must be positive: {raw!r}")
    return amount, currency


def _norm(s: str) -> str:
    # Уніфікуємо апострофи (', ʼ, ’) — назви на кшталт «Здоров'я» пишуть по-різному
    return re.sub(r"[ʼ’`]", "'", s).strip().lower()


def pick_category(merchant: str, categories: list[Category]) -> Category | None:
    """Категорія за ключовими словами продавця → fallback «Інше» → None."""
    by_name = {_norm(c.name): c for c in categories}
    merchant_n = _norm(merchant or "")

    if merchant_n:
        for rule in CATEGORY_RULES:
            if any(_norm(kw) in merchant_n for kw in rule["keywords"]):
                for name in rule["categories"]:
                    if _norm(name) in by_name:
                        return by_name[_norm(name)]

    for name in FALLBACK_CATEGORY_NAMES:
        if _norm(name) in by_name:
            return by_name[_norm(name)]
    return None


def pick_account(card: str, accounts: list[Account]) -> Account | None:
    """Рахунок, чия назва/keywords збігаються з назвою картки → рахунок за
    замовчуванням → найстаріший рахунок."""
    if not accounts:
        return None
    card_n = _norm(card or "")
    if card_n:
        for acc in accounts:
            names = [acc.name, *(k for k in (acc.keywords or []) if isinstance(k, str))]
            if any(n and (_norm(n) in card_n or card_n in _norm(n)) for n in names):
                return acc
    return next((a for a in accounts if a.is_default), None) or min(accounts, key=lambda a: a.id)


async def find_recent_duplicate(
    db: AsyncSession, user_id: int, amount: float, merchant: str | None, card: str | None,
) -> Transaction | None:
    """Wallet-запис з тією ж сумою, продавцем і карткою за останні 60 с."""
    since = datetime.utcnow() - DEDUP_WINDOW
    res = await db.execute(
        select(Transaction)
        .where(
            and_(
                Transaction.user_id == user_id,
                Transaction.source == WALLET_SOURCE,
                Transaction.amount == amount,
                Transaction.merchant.is_(None) if merchant is None else Transaction.merchant == merchant,
                Transaction.card.is_(None) if card is None else Transaction.card == card,
                Transaction.date >= since,
            )
        )
        .order_by(Transaction.date.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()
