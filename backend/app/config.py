from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Telegram (порожній рядок = бот не запускається, але API стартує)
    TELEGRAM_BOT_TOKEN: str = ""
    WEBHOOK_URL: str = ""

    # Окремий бот-фінансовий асистент (Money Deck Advisor)
    ADVISOR_BOT_TOKEN: str = ""

    # Anthropic Claude (порожній рядок = AI-виклики повернуть помилку gracefully)
    ANTHROPIC_API_KEY: str = ""

    # База даних
    DATABASE_URL: str = "sqlite+aiosqlite:///./finance.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def fix_async_driver(cls, v: str) -> str:
        # Railway передає postgres:// або postgresql:// — замінюємо на asyncpg-драйвер
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    # Обмінні курси
    NBU_API_URL: str = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
    COINGECKO_API_URL: str = "https://api.coingecko.com/api/v3"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Кеш курсів (секунди)
    EXCHANGE_RATE_CACHE_TTL: int = 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
