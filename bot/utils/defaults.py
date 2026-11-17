from app.database import AsyncSessionLocal
from app.models import Category

BASE_CATEGORIES = [
    # Витрати
    {"name": "Еда",        "type": "expense", "icon": "🍔", "color": "#f05252"},
    {"name": "Транспорт",  "type": "expense", "icon": "🚗", "color": "#f0a050"},
    {"name": "Развлечения",    "type": "expense", "icon": "🎮", "color": "#a855f7"},
    {"name": "Здоровье",   "type": "expense", "icon": "💊", "color": "#4caf82"},
    {"name": "Одежда",       "type": "expense", "icon": "👕", "color": "#5557f5"},
    {"name": "Коммуналка", "type": "expense", "icon": "🏠", "color": "#f59e0b"},
    {"name": "Другое",       "type": "expense", "icon": "💸", "color": "#8892b0"},
    # Доходи
    {"name": "Зарплата",   "type": "income",  "icon": "💼", "color": "#4caf82"},
    {"name": "Фриланс",    "type": "income",  "icon": "💻", "color": "#5557f5"},
    {"name": "Другое",       "type": "income",  "icon": "💰", "color": "#8892b0"},
]


async def create_default_categories(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        for cat in BASE_CATEGORIES:
            db.add(Category(user_id=user_id, **cat))
        await db.commit()
