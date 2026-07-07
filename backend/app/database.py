import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# connect_args потрібен тільки для SQLite (check_same_thread)
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
    # PostgreSQL: pool налаштування для Railway
    pool_pre_ping=True,                          # перевіряє з'єднання перед використанням
    **({} if _is_sqlite else {"pool_size": 5, "max_overflow": 10}),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


_PG_MIGRATIONS = [
    # transactions ─────────────────────────────────────────────────
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS source     VARCHAR(16) DEFAULT 'manual' NOT NULL",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS amount_uah FLOAT       DEFAULT 0.0     NOT NULL",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency   VARCHAR(10) DEFAULT 'UAH'   NOT NULL",
    "UPDATE transactions SET source     = 'manual' WHERE source IS NULL",
    "UPDATE transactions SET amount_uah = amount   WHERE amount_uah IS NULL",
    "UPDATE transactions SET currency   = 'UAH'   WHERE currency IS NULL",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS external_id VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_transactions_external_id ON transactions (external_id)",
    # debts ─────────────────────────────────────────────────────────
    "ALTER TABLE debts ADD COLUMN IF NOT EXISTS currency          VARCHAR(10) DEFAULT 'UAH' NOT NULL",
    "ALTER TABLE debts ADD COLUMN IF NOT EXISTS next_payment_date DATE",
    "ALTER TABLE debts ADD COLUMN IF NOT EXISTS monthly_payment   FLOAT       DEFAULT 0.0   NOT NULL",
    "ALTER TABLE debts ADD COLUMN IF NOT EXISTS interest_rate     FLOAT       DEFAULT 0.0   NOT NULL",
    "UPDATE debts SET currency       = 'UAH' WHERE currency IS NULL",
    "UPDATE debts SET monthly_payment = 0    WHERE monthly_payment IS NULL",
    "UPDATE debts SET interest_rate   = 0    WHERE interest_rate IS NULL",
    # goals ─────────────────────────────────────────────────────────
    "ALTER TABLE goals ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'UAH' NOT NULL",
    "UPDATE goals SET currency = 'UAH' WHERE currency IS NULL",
    # accounts ──────────────────────────────────────────────────────
    "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE NOT NULL",
    "UPDATE accounts SET is_default = FALSE WHERE is_default IS NULL",
]


async def init_db() -> None:
    """Створює всі таблиці при старті."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Міграції — кожна у своїй транзакції, щоб помилка одного
    # кроку не зупиняла всю ланцюжку через PostgreSQL abort-стан.
    if not _is_sqlite:
        for stmt in _PG_MIGRATIONS:
            async with engine.begin() as conn:
                try:
                    await conn.execute(text(stmt))
                except Exception as exc:
                    logger.warning("Migration skipped (%s): %.80s", exc.__class__.__name__, stmt)


async def get_db() -> AsyncSession:
    """FastAPI dependency — повертає async-сесію."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
