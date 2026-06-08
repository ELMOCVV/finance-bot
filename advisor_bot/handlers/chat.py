import logging

import anthropic
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select, and_

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import ChatHistory, User
from advisor_bot.services.context import build_user_context

logger = logging.getLogger(__name__)
router = Router()

BOT_TYPE = "advisor"
HISTORY_LIMIT = 10
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT_TEMPLATE = (
    "Ти Money Deck Advisor — персональний фінансовий асистент.\n"
    "Спілкуєшся як друг, коротко і по суті.\n"
    "Знаєш реальні фінанси юзера:\n"
    "{context}\n\n"
    "Відповідай українською. Без markdown символів.\n"
    "Максимум 3-5 речень якщо не потрібен детальний аналіз."
)

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    name = db_user.first_name or (message.from_user.first_name if message.from_user else None) or "друже"
    await message.answer(
        f"Привіт, {name}! 👋\n\n"
        "Я Money Deck Advisor — твій персональний фінансовий асистент. "
        "Я бачу твої рахунки, транзакції, борги, цілі, підписки і бюджети — "
        "питай про що завгодно, і я допоможу розібратись із грошима."
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_message(message: Message, db_user: User) -> None:
    text = (message.text or "").strip()
    if not text:
        return

    await message.bot.send_chat_action(message.chat.id, "typing")

    context = await build_user_context(db_user.id)
    history = await _load_history(db_user.id)

    try:
        response = await _client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT_TEMPLATE.format(context=context),
            messages=history + [{"role": "user", "content": text}],
        )
        answer = response.content[0].text
    except Exception as e:
        logger.error("Помилка Claude API (advisor): %s", e)
        answer = "Вибач, зараз не можу відповісти — спробуй трохи пізніше."

    await _save_message(db_user.id, "user", text)
    await _save_message(db_user.id, "assistant", answer)

    await message.answer(answer)


async def _load_history(user_id: int, limit: int = HISTORY_LIMIT) -> list[dict]:
    """Останні `limit` повідомлень advisor-чату для юзера, у хронологічному порядку."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatHistory)
            .where(and_(ChatHistory.user_id == user_id, ChatHistory.bot_type == BOT_TYPE))
            .order_by(ChatHistory.id.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
    return [{"role": row.role, "content": row.message} for row in rows]


async def _save_message(user_id: int, role: str, content: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(ChatHistory(user_id=user_id, bot_type=BOT_TYPE, role=role, message=content))
        await db.commit()
