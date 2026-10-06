"""Apple Wallet (iOS «Команди») → витрата.

Парсинг суми з текстом валюти, очистка назви картки, підбір категорії
(запамʼятовані продавці → словник ключових слів → «Інше»), вибір рахунку
(привʼязка картки → підказка за ключовими словами → рахунок за замовчуванням)
та дедуплікація. Сам запис транзакції — через спільний create_transaction_record.
"""
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Category, Transaction, MerchantCategory, WalletCard, WalletPending
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


def clean_card(card: str | None, merchant: str | None) -> str | None:
    """iOS склеює назву картки з продавцем: "monobankYidalniaYidalnia" → "monobank"."""
    if not card:
        return None
    if merchant:
        card = re.sub(re.escape(merchant), "", card, flags=re.IGNORECASE)
    card = card.strip()
    return card or None


def normalize_key(value: str, max_len: int = 64) -> str:
    """Ключ для довідників: нижній регістр, уніфіковані апострофи й пробіли."""
    return re.sub(r"\s+", " ", _norm(value))[:max_len]


def _norm(s: str) -> str:
    # Уніфікуємо апострофи (', ʼ, ’) — назви на кшталт «Здоров'я» пишуть по-різному
    return re.sub(r"[ʼ’`]", "'", s).strip().lower()


def pick_category(
    merchant: str, categories: list[Category], remembered_id: int | None = None,
) -> Category | None:
    """Запамʼятована для продавця категорія → ключові слова → fallback «Інше» → None."""
    if remembered_id is not None:
        remembered = next((c for c in categories if c.id == remembered_id), None)
        if remembered:
            return remembered
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


async def find_recent_pending_duplicate(
    db: AsyncSession, user_id: int, amount: float, merchant: str | None, card: str | None,
) -> WalletPending | None:
    """Те саме, що find_recent_duplicate, але для відкладених витрат (немає рахунків)."""
    since = datetime.utcnow() - DEDUP_WINDOW
    res = await db.execute(
        select(WalletPending)
        .where(
            and_(
                WalletPending.user_id == user_id,
                WalletPending.amount == amount,
                WalletPending.merchant.is_(None) if merchant is None else WalletPending.merchant == merchant,
                WalletPending.card.is_(None) if card is None else WalletPending.card == card,
                WalletPending.created_at >= since,
            )
        )
        .limit(1)
    )
    return res.scalar_one_or_none()


# ── Запамʼятовані категорії продавців ─────────────────────────────────────────

async def get_remembered_category_id(db: AsyncSession, user_id: int, merchant: str | None) -> int | None:
    if not merchant:
        return None
    res = await db.execute(
        select(MerchantCategory.category_id).where(
            and_(MerchantCategory.user_id == user_id,
                 MerchantCategory.merchant_key == normalize_key(merchant, 128))
        )
    )
    return res.scalar_one_or_none()


async def remember_merchant_category(db: AsyncSession, user_id: int, merchant: str | None, category_id: int) -> None:
    if not merchant:
        return
    key = normalize_key(merchant, 128)
    res = await db.execute(
        select(MerchantCategory).where(
            and_(MerchantCategory.user_id == user_id, MerchantCategory.merchant_key == key)
        )
    )
    row = res.scalar_one_or_none()
    if row:
        row.category_id = category_id
    else:
        db.add(MerchantCategory(user_id=user_id, merchant_key=key, category_id=category_id))
    await db.flush()


# ── Привʼязки карток до рахунків ──────────────────────────────────────────────

async def get_card_binding(db: AsyncSession, user_id: int, card: str | None) -> WalletCard | None:
    if not card:
        return None
    res = await db.execute(
        select(WalletCard).where(
            and_(WalletCard.user_id == user_id, WalletCard.card_key == normalize_key(card))
        )
    )
    return res.scalar_one_or_none()


async def bind_card(db: AsyncSession, user_id: int, card: str, account_id: int) -> WalletCard:
    binding = await get_card_binding(db, user_id, card)
    if binding:
        binding.account_id = account_id
        binding.card_name = card[:64]
    else:
        binding = WalletCard(user_id=user_id, card_name=card[:64], card_key=normalize_key(card), account_id=account_id)
        db.add(binding)
    await db.flush()
    return binding
