import os
import sys
import tempfile
from pathlib import Path

# Тести запускаються з кореня репозиторію: `pytest backend/tests`.
# БД — тимчасовий SQLite-файл; змінні мають бути задані ДО імпорту app.*
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND.parent))  # пакет bot/ (обробники Telegram)
_tmp_dir = tempfile.mkdtemp(prefix="finance-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_dir}/test.db"
os.environ.setdefault("BOT_EMBEDDED", "false")


async def wipe_db() -> None:
    """Очищає всі таблиці (у SQLite FK-каскади не спрацьовують — чистимо явно)."""
    from app.database import Base, engine
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
