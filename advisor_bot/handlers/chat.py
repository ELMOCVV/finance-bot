import logging
from itertools import count

import anthropic
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, and_

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import ChatHistory, User
from advisor_bot.services.context import build_user_context
from advisor_bot.services import actions

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
    "Ти можеш не лише радити, а й ВИКОНУВАТИ дії інструментами: коригувати\n"
    "баланс, створювати/оновлювати цілі, змінювати ліміт бюджету, створювати\n"
    "борги, вносити платежі по боргах. Пропонуй такі дії сам, коли це доречно.\n"
    "ВАЖЛИВО: викликай інструмент ЛИШЕ коли маєш конкретні деталі (точні суми,\n"
    "назви рахунків/цілей/боргів/категорій саме як у контексті вище, строки).\n"
    "Якщо юзер лише висловив намір ('хочу на море'), а сум/деталей немає —\n"
    "НЕ викликай інструмент, а перепитай по-людськи. Назви бери з контексту.\n"
    "Кожну дію користувач ще підтвердить кнопкою — тобі не треба питати дозволу\n"
    "текстом, просто виклич інструмент з даними.\n"
    "Відповідай мовою користувача. Без markdown символів.\n"
    "Максимум 3-5 речень якщо не потрібен детальний аналіз."
)

_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Одна дія в очікуванні підтвердження на юзера (in-memory, привʼязано до user_id).
_pending: dict[int, dict] = {}
_token_counter = count(1)


def _confirm_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Так", callback_data=f"adv:ok:{token}"),
        InlineKeyboardButton(text="❌ Скасувати", callback_data=f"adv:cancel:{token}"),
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    name = db_user.first_name or (message.from_user.first_name if message.from_user else None) or "друже"
    await message.answer(
        f"Привіт, {name}! 👋\n\n"
        "Я Money Deck Advisor — твій персональний фінансовий асистент. "
        "Я бачу твої рахунки, транзакції, борги, цілі, підписки і бюджети — "
        "питай про що завгодно, і я допоможу розібратись із грошима. "
        "Можу навіть сам оновити баланс, ціль чи бюджет — лише підтвердиш."
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
            tools=actions.TOOLS,
            messages=history + [{"role": "user", "content": text}],
        )
    except Exception as e:
        logger.error("Помилка Claude API (advisor): %s", e)
        await message.answer("Вибач, зараз не можу відповісти — спробуй трохи пізніше.")
        return

    text_parts = [b.text for b in response.content if b.type == "text"]
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)

    await _save_message(db_user.id, "user", text)

    # Claude обрав дію → готуємо і показуємо підтвердження (НЕ виконуємо одразу)
    if tool_use is not None:
        prepared, error = await actions.prepare(db_user.id, tool_use.name, tool_use.input or {})
        if prepared:
            token = str(next(_token_counter))
            prepared["token"] = token
            _pending[db_user.id] = prepared
            lead = (text_parts[0].strip() + "\n\n") if text_parts and text_parts[0].strip() else ""
            card = lead + prepared["confirm_text"]
            await _save_message(db_user.id, "assistant", card)
            await message.answer(card, reply_markup=_confirm_keyboard(token))
            return
        # Не вдалося зарезолвити — відповідаємо текстом (Claude або помилка)
        answer = (text_parts[0].strip() if text_parts and text_parts[0].strip() else error) or error
        await _save_message(db_user.id, "assistant", answer)
        await message.answer(answer)
        return

    answer = "\n".join(p for p in text_parts if p).strip() or "Вибач, не зрозумів. Можеш переформулювати?"
    await _save_message(db_user.id, "assistant", answer)
    await message.answer(answer)


@router.callback_query(F.data.startswith("adv:ok:"))
async def confirm_action(callback: CallbackQuery, db_user: User) -> None:
    token = callback.data.split(":")[2]
    prepared = _pending.get(db_user.id)
    if not prepared or prepared.get("token") != token:
        await callback.answer("Ця дія вже неактуальна", show_alert=True)
        return
    _pending.pop(db_user.id, None)
    await callback.answer("Виконую…")
    success, error = await actions.execute(db_user.id, prepared)
    result = success or error or "Не вдалося виконати дію."
    await _save_message(db_user.id, "assistant", result)
    try:
        await callback.message.edit_text(result)
    except Exception:
        await callback.message.answer(result)


@router.callback_query(F.data.startswith("adv:cancel:"))
async def cancel_action(callback: CallbackQuery, db_user: User) -> None:
    token = callback.data.split(":")[2]
    prepared = _pending.get(db_user.id)
    if prepared and prepared.get("token") == token:
        _pending.pop(db_user.id, None)
    await callback.answer()
    try:
        await callback.message.edit_text("❌ Скасовано.")
    except Exception:
        pass


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
