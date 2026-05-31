from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User
from bot.keyboards.inline import main_menu_keyboard
from bot.states import Registration
from bot.utils.defaults import create_default_categories

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, state: FSMContext) -> None:
    # Якщо first_name вже збережено — реєстрація завершена
    if db_user.first_name:
        await message.answer(
            f"👋 Ви вже зареєстровані, <b>{db_user.first_name}</b>!\n\nГоловне меню:",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Новий користувач — запитуємо ім'я
    await state.set_state(Registration.waiting_name)
    await message.answer(
        "👋 Привіт! Я — <b>FinanceAI Bot</b>, твій розумний фінансовий помічник.\n\n"
        "Як тебе звати? Введи своє ім'я:",
    )


@router.message(Registration.waiting_name)
async def save_name(message: Message, db_user: User, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 64:
        await message.answer("Будь ласка, введи ім'я (до 64 символів):")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == db_user.id))
        user = result.scalar_one()
        user.first_name = name
        await db.commit()

    await create_default_categories(db_user.id)
    await state.clear()

    await message.answer(
        f"🎉 Вітаємо, <b>{name}</b>! Реєстрація завершена.\n\n"
        f"Я створив для тебе базові категорії витрат і доходів.\n\n"
        f"Першим кроком — додай рахунок (картка, готівка тощо):",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Головне меню:", reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📚 <b>Як користуватись FinanceAI Bot:</b>\n\n"
        "<b>Додати транзакцію:</b>\n"
        "• Натисни «💸 Додати витрату» або просто напиши текст\n"
        "• Наприклад: <i>«Кава 50 грн»</i> або <i>«Зарплата 15000»</i>\n"
        "• Або надішли фото чека через кнопку «📷 Фото чека»\n\n"
        "<b>Команди:</b>\n"
        "/start — головне меню\n"
        "/menu — відкрити меню\n"
        "/help — ця довідка",
    )
