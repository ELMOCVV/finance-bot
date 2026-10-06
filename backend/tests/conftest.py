import os
import sys
import tempfile
from pathlib import Path

# Тести запускаються з кореня репозиторію: `pytest backend/tests`.
# БД — тимчасовий SQLite-файл; змінні мають бути задані ДО імпорту app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_tmp_dir = tempfile.mkdtemp(prefix="finance-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_dir}/test.db"
os.environ.setdefault("BOT_EMBEDDED", "false")
