import base64
import logging

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.models import User
from app.services.claude_service import claude_service
from bot.handlers.transaction import _parse_and_show

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.photo)
async def handle_receipt_photo(message: Message, bot: Bot, db_user: User, state: FSMContext) -> None:
    """Розпізнає чек із фото, потім передає в стандартний confirmation-flow."""
    await message.answer("📸 Розпізнаю чек...")

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_b64 = base64.b64encode(file_bytes.read()).decode()

    parsed = await claude_service.parse_receipt_photo(image_b64, media_type="image/jpeg")

    if "error" in parsed:
        await message.answer(
            f"❌ Не вдалось розпізнати чек: {parsed['error']}\n\n"
            "Спробуй зробити чіткіше фото на рівній поверхні."
        )
        return

    # Якщо Claude повернув список — беремо перший запис
    if isinstance(parsed, list):
        if not parsed:
            await message.answer("❌ На фото не знайдено транзакцій.")
            return
        parsed = parsed[0]

    # Будуємо текстовий опис для стандартного flow
    amount = parsed.get("amount", 0)
    currency = parsed.get("currency", "UAH")
    desc = parsed.get("description", "Чек")
    tx_type = parsed.get("type", "expense")
    synthetic_text = f"{desc} {amount} {currency}"

    # Передаємо у стандартний парсинг (з підбором категорії)
    # Замість claude_service.parse_transaction підставляємо вже розпарсений результат
    await state.update_data(_photo_parsed=parsed)
    await _parse_and_show_photo(message, db_user, parsed, state)


async def _parse_and_show_photo(message: Message, db_user: User, parsed: dict, state: FSMContext) -> None:
    """Аналог _parse_and_show, але з уже готовим parsed dict із фото."""
    from sqlalchemy import select, and_
    from app.database import AsyncSessionLocal
    from app.models import Account, Category
    from bot.services.category_matcher import match_category
    from bot.utils.tx_helpers import build_confirmation_text
    from bot.keyboards.inline import (
        accounts_list_keyboard, confirm_transaction_keyboard, new_category_keyboard
    )
    from bot.handlers.transaction import _find_account

    async with AsyncSessionLocal() as db:
        acc_res = await db.execute(select(Account).where(Account.user_id == db_user.id))
        accounts = acc_res.scalars().all()

    if not accounts:
        await message.answer(
            "⚠️ У вас ще немає рахунків. Спочатку створіть рахунок:",
            reply_markup=accounts_list_keyboard([]),
        )
        return

    tx_type = parsed.get("type", "expense")
    account = _find_account(accounts, parsed.get("account_hint"))

    async with AsyncSessionLocal() as db:
        cat_res = await db.execute(
            select(Category).where(
                and_(Category.user_id == db_user.id, Category.type == tx_type)
            )
        )
        user_cats = cat_res.scalars().all()

    cat_match = await match_category(
        description=parsed.get("description", ""),
        hint=parsed.get("category_hint", ""),
        tx_type=tx_type,
        user_categories=[{"id": c.id, "name": c.name} for c in user_cats],
    )

    state_data = {
        "parsed": parsed,
        "tx_type": tx_type,
        "amount": parsed.get("amount"),
        "currency": parsed.get("currency", "UAH"),
        "description": parsed.get("description"),
        "account_id": account.id,
        "account_name": account.name,
        "source": "bot_photo",
    }

    if "matched_id" in cat_match:
        state_data.update(category_id=cat_match["matched_id"], category_name=cat_match["name"], is_new_cat=False)
        keyboard = confirm_transaction_keyboard()
    else:
        state_data.update(category_id=None, category_name="—", is_new_cat=True, new_cat_name=cat_match.get("new_name", "Інше"))
        keyboard = new_category_keyboard(state_data["new_cat_name"])

    await state.update_data(**state_data)
    await message.answer(build_confirmation_text(state_data), reply_markup=keyboard)
