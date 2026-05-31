from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


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


async def init_db() -> None:
    """Створює всі таблиці при старті."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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
