from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Telegram (порожній рядок = бот не запускається, але API стартує)
    TELEGRAM_BOT_TOKEN: str = ""
    WEBHOOK_URL: str = ""

    # Anthropic Claude (порожній рядок = AI-виклики повернуть помилку gracefully)
    ANTHROPIC_API_KEY: str = ""

    # База даних
    DATABASE_URL: str = "sqlite+aiosqlite:///./finance.db"

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
