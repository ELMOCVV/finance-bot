from app.database import AsyncSessionLocal
from app.models import Category

BASE_CATEGORIES = [
    # Витрати
    {"name": "Їжа",        "type": "expense", "icon": "🍔", "color": "#f05252"},
    {"name": "Транспорт",  "type": "expense", "icon": "🚗", "color": "#f0a050"},
    {"name": "Розваги",    "type": "expense", "icon": "🎮", "color": "#a855f7"},
    {"name": "Здоров'я",   "type": "expense", "icon": "💊", "color": "#4caf82"},
    {"name": "Одяг",       "type": "expense", "icon": "👕", "color": "#5557f5"},
    {"name": "Комунальні", "type": "expense", "icon": "🏠", "color": "#f59e0b"},
    {"name": "Інше",       "type": "expense", "icon": "💸", "color": "#8892b0"},
    # Доходи
    {"name": "Зарплата",   "type": "income",  "icon": "💼", "color": "#4caf82"},
    {"name": "Фріланс",    "type": "income",  "icon": "💻", "color": "#5557f5"},
    {"name": "Інше",       "type": "income",  "icon": "💰", "color": "#8892b0"},
]


async def create_default_categories(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        for cat in BASE_CATEGORIES:
            db.add(Category(user_id=user_id, **cat))
        await db.commit()
