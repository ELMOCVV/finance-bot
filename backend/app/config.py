from pydantic_settings import BaseSettings
from pydantic import field_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Telegram (порожній рядок = бот не запускається, але API стартує)
    TELEGRAM_BOT_TOKEN: str = ""
    WEBHOOK_URL: str = ""

    # Публічна база для вхідних webhook-ів банків (Monobank).
    # Наприклад: https://money-deck.up.railway.app
    # Якщо порожньо — використовується WEBHOOK_URL.
    WEBHOOK_BASE_URL: str = ""

    # Ключ шифрування банківських токенів (Fernet). Будь-який рядок —
    # якщо це не валідний Fernet-ключ, з нього деривується 32-байтний ключ.
    TOKEN_ENCRYPTION_KEY: str = ""

    # Базовий URL Monobank Open API
    MONOBANK_API_URL: str = "https://api.monobank.ua"

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
