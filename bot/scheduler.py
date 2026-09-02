import logging
import time
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models.subscription import Subscription
from app.models.account import Account
from app.models.user import User
from app.models import BankConnection, BankCard

logger = logging.getLogger(__name__)

# Вікно досвірки: 3 години запасу, щоб перекрити затримку фіналізації hold.
_RECONCILE_WINDOW_SECONDS = 3 * 60 * 60

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


async def reconcile_monobank() -> None:
    """Страховка на випадок пропущених Monobank-webhook (напр. коли webhook
    прийшов лише з hold=true, а фінальний з hold=false так і не надійшов).

    Кожні 20 хв проходить по всіх підключеннях з відстежуваними картками,
    тягне виписку за останні 3 години і прогонить кожну фіналізовану операцію
    (hold=false) через _process_statement_item. Дедуп по external_id відсіює
    вже оброблене, тож повторні запуски не дублюють транзакції чи confirm-и.
    Помилка на одному підключенні/картці не зупиняє решту.
    """
    # Лінивий імпорт — уникаємо циклічної залежності scheduler ↔ handlers.
    from bot.handlers.monobank import _process_statement_item
    from app.services import token_crypto
    from app.services.monobank_service import monobank_service

    now = int(time.time())
    from_ts = now - _RECONCILE_WINDOW_SECONDS

    async with AsyncSessionLocal() as db:
        connections = (await db.execute(select(BankConnection))).scalars().all()

    processed_conns = 0
    for conn in connections:
        try:
            token = token_crypto.decrypt_token(conn.encrypted_token)
            async with AsyncSessionLocal() as db:
                cards = (await db.execute(
                    select(BankCard).where(
                        and_(BankCard.connection_id == conn.id, BankCard.is_tracked == True)
                    )
                )).scalars().all()

            for card in cards:
                try:
                    # get_statement дотримується throttle 60 с — послідовно, не паралельно
                    items = await monobank_service.get_statement(
                        token, card.mono_account_id, from_ts, now
                    )
                except Exception as e:
                    logger.warning(
                        "Reconcile: statement failed (connection_id=%s, mono_account_id=%s): %s",
                        conn.id, card.mono_account_id, e.__class__.__name__,
                    )
                    continue

                logger.info(
                    "Reconcile: fetched %d items (connection_id=%s, mono_account_id=%s)",
                    len(items), conn.id, card.mono_account_id,
                )
                for item in items:
                    # hold блокує лише витрати — вони можуть ще змінитись/скасуватись;
                    # надходження (amount > 0) фінальні одразу, тож пропускаємо їх далі.
                    if item.get("hold") is True and item.get("amount", 0) < 0:
                        logger.info(
                            "Reconcile: expense still hold=true, skipping (connection_id=%s, "
                            "mono_account_id=%s, item_id=%s)",
                            conn.id, card.mono_account_id, item.get("id"),
                        )
                        continue  # ще не фіналізовано — чекаємо наступного циклу
                    await _process_statement_item(conn.id, card.mono_account_id, item)
            processed_conns += 1
        except Exception as e:
            logger.error("Reconcile failed for connection_id=%s: %s", conn.id, e, exc_info=True)

    if connections:
        logger.info("Monobank reconcile finished: %d/%d connections", processed_conns, len(connections))


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
    scheduler.add_job(
        reconcile_monobank,
        trigger="interval",
        minutes=20,
        id="monobank_reconcile",
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info("Планувальник налаштовано (підписки щогодини, Monobank-досвірка кожні 20 хв)")
    return scheduler
