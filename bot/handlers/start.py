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
            f"👋 Ты уже зарегистрирован, <b>{db_user.first_name}</b>!\n\nГлавное меню:",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Новий користувач — запитуємо ім'я
    await state.set_state(Registration.waiting_name)
    await message.answer(
        "👋 Привет! Я — <b>FinanceAI Bot</b>, твой умный финансовый помощник.\n\n"
        "Как тебя зовут? Введи своё имя:",
    )


@router.message(Registration.waiting_name)
async def save_name(message: Message, db_user: User, state: FSMContext) -> None:
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 64:
        await message.answer("Пожалуйста, введи имя (до 64 символов):")
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == db_user.id))
        user = result.scalar_one()
        user.first_name = name
        await db.commit()

    await create_default_categories(db_user.id)
    await state.clear()

    await message.answer(
        f"🎉 Поздравляю, <b>{name}</b>! Регистрация завершена.\n\n"
        f"Я создал для тебя базовые категории расходов и доходов.\n\n"
        f"Первым шагом — добавь счёт (карта, наличные и т.д.):",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📚 <b>Как пользоваться FinanceAI Bot:</b>\n\n"
        "<b>Добавить транзакцию:</b>\n"
        "• Нажми «💸 Расход» или просто напиши текст\n"
        "• Например: <i>«Кофе 50 грн»</i> или <i>«Зарплата 15000»</i>\n"
        "• Или пришли фото чека через кнопку «📷 Фото чека»\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/menu — открыть меню\n"
        "/cards — привязки карт Apple Wallet\n"
        "/help — эта справка",
    )
