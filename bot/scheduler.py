import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.account import Account
from app.models.user import User

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def check_subscriptions(bot) -> None:
    """Щогодинна перевірка: надсилає нагадування якщо завтра день списання."""
    now = datetime.utcnow()
    tomorrow = now + timedelta(days=1)
    current_hour = now.hour

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Subscription).where(
                and_(
                    Subscription.is_active == True,
                    Subscription.remind_hour == current_hour,
                )
            )
        )
        subscriptions = result.scalars().all()

        for sub in subscriptions:
            # Визначаємо чи завтра день списання
            if sub.period == "monthly":
                should_notify = sub.day_of_month == tomorrow.day
            else:  # yearly
                should_notify = (
                    sub.day_of_month == tomorrow.day
                    and sub.month_of_year == tomorrow.month
                )

            if not should_notify:
                continue

            # Отримуємо telegram_id юзера
            user = await db.get(User, sub.user_id)
            if not user:
                continue

            # Формуємо текст нагадування
            day_str = f"{sub.day_of_month}-го"
            text = (
                f"⚠️ <b>Нагадування про підписку</b>\n\n"
                f"🔔 {sub.name}\n"
                f"💸 {sub.amount:.2f} {sub.currency} списується завтра ({day_str})\n"
            )

            if sub.account_id:
                account = await db.get(Account, sub.account_id)
                if account:
                    balance_info = f"🏦 Рахунок «{account.name}»: {account.balance:.2f} {account.currency}"
                    if account.balance < sub.amount:
                        balance_info += " — ⚠️ можливо варто поповнити!"
                    text += balance_info

            try:
                await bot.send_message(user.telegram_id, text, parse_mode="HTML")
                logger.info(
                    "Надіслано нагадування для user=%s, підписка=%s",
                    user.telegram_id, sub.name
                )
            except Exception as e:
                logger.error("Помилка надсилання нагадування user=%s: %s", user.telegram_id, e)


def setup_scheduler(bot) -> AsyncIOScheduler:
    """Реєструє завдання і повертає планувальник."""
    scheduler.add_job(
        check_subscriptions,
        trigger="cron",
        minute=0,       # запуск кожну годину в :00
        args=[bot],
        id="subscription_checker",
        replace_existing=True,
        misfire_grace_time=300,  # дозволяємо 5 хв запізнення
    )
    logger.info("Планувальник підписок налаштовано (щогодини в :00)")
    return scheduler
