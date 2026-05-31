from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User


class UserMiddleware(BaseMiddleware):
    """Автоматично створює/оновлює користувача з БД при кожному апдейті."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TelegramUser | None = data.get("event_from_user")

        if tg_user and not tg_user.is_bot:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(User).where(User.telegram_id == tg_user.id)
                )
                user = result.scalar_one_or_none()

                if not user:
                    # Новий юзер: first_name НЕ зберігаємо —
                    # воно стане маркером завершення реєстрації
                    user = User(
                        telegram_id=tg_user.id,
                        username=tg_user.username,
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    data["is_new_user"] = True
                else:
                    data["is_new_user"] = False
                    # Оновлюємо username якщо змінився
                    if user.username != tg_user.username:
                        user.username = tg_user.username
                        await db.commit()

                data["db_user"] = user

        return await handler(event, data)
