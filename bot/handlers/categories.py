from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, and_

from app.database import AsyncSessionLocal
from app.models import User, Category
from bot.keyboards.inline import (
    categories_manage_keyboard,
    category_type_keyboard,
    confirm_delete_keyboard,
    back_keyboard,
)
from bot.states import AddCategory, EditCategory

router = Router()

_TYPE_LABELS = {"expense": "💸 витрата", "income": "💰 дохід"}


async def _show_categories(target, db_user: User) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Category).where(Category.user_id == db_user.id).order_by(Category.type, Category.name)
        )
        categories = result.scalars().all()

    if categories:
        lines = ["🏷 <b>Ваші категорії:</b>\n"]
        for cat in categories:
            lines.append(f"{cat.icon or '🏷'} <b>{cat.name}</b> — {_TYPE_LABELS.get(cat.type, cat.type)}")
        text = "\n".join(lines)
    else:
        text = "🏷 <b>Категорій поки немає.</b>\nДодайте першу:"

    kb = categories_manage_keyboard(categories)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)
        await target.answer()
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:categories")
async def show_categories(callback: CallbackQuery, db_user: User) -> None:
    await _show_categories(callback, db_user)


# ── Додавання ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cat:add")
async def start_add_category(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddCategory.waiting_name)
    await callback.message.edit_text(
        "🏷 <b>Нова категорія</b>\n\nВведіть назву категорії:\n"
        "<i>Наприклад: Подарунки, Інвестиції</i>",
        reply_markup=back_keyboard("menu:categories"),
    )
    await callback.answer()


@router.message(AddCategory.waiting_name)
async def category_get_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 128:
        await message.answer("Введіть коректну назву (до 128 символів):")
        return
    await state.update_data(cat_name=name)
    await state.set_state(AddCategory.waiting_type)
    await message.answer(
        f"🏷 Категорія: <b>{name}</b>\n\nОберіть тип:",
        reply_markup=category_type_keyboard(),
    )


@router.callback_query(AddCategory.waiting_type, F.data.startswith("cattype:"))
async def category_get_type(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    cat_type = callback.data.split(":")[1]
    data = await state.get_data()
    name = data["cat_name"]

    async with AsyncSessionLocal() as db:
        db.add(Category(user_id=db_user.id, name=name, type=cat_type))
        await db.commit()

    await state.clear()
    await callback.answer(f"✅ Категорію «{name}» додано!", show_alert=True)
    await _show_categories(callback, db_user)


# ── Редагування назви ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:rename:"))
async def category_rename_prompt(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    cat_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).where(and_(Category.id == cat_id, Category.user_id == db_user.id)))
        cat = result.scalar_one_or_none()

    if not cat:
        await callback.answer("Категорію не знайдено")
        return

    await state.set_state(EditCategory.waiting_name)
    await state.update_data(edit_cat_id=cat_id)
    await callback.message.edit_text(
        f"📝 Поточна назва: «<b>{cat.name}</b>»\n\nВведіть нову назву:",
        reply_markup=back_keyboard("menu:categories"),
    )
    await callback.answer()


@router.message(EditCategory.waiting_name)
async def category_rename_input(message: Message, state: FSMContext, db_user: User) -> None:
    new_name = (message.text or "").strip()
    if not new_name or len(new_name) > 128:
        await message.answer("Введіть коректну назву (до 128 символів):")
        return

    data = await state.get_data()
    cat_id = data["edit_cat_id"]
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).where(and_(Category.id == cat_id, Category.user_id == db_user.id)))
        cat = result.scalar_one_or_none()
        if cat:
            cat.name = new_name
            await db.commit()

    await state.clear()
    await message.answer(f"✅ Назву змінено на «{new_name}»")
    await _show_categories(message, db_user)


# ── Видалення ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:del_confirm:"))
async def category_del_confirm(callback: CallbackQuery, db_user: User) -> None:
    cat_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).where(and_(Category.id == cat_id, Category.user_id == db_user.id)))
        cat = result.scalar_one_or_none()
    name = cat.name if cat else f"#{cat_id}"
    await callback.message.edit_text(
        f"⚠️ Видалити категорію «<b>{name}</b>»?\n\n"
        "Транзакції залишаться без категорії, а пов'язані бюджети будуть видалені.",
        reply_markup=confirm_delete_keyboard(
            confirm_cb=f"cat:delete:{cat_id}",
            cancel_cb="menu:categories",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:delete:"))
async def category_delete(callback: CallbackQuery, db_user: User) -> None:
    cat_id = int(callback.data.split(":")[2])
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).where(and_(Category.id == cat_id, Category.user_id == db_user.id)))
        cat = result.scalar_one_or_none()
        if cat:
            await db.delete(cat)
            await db.commit()
    await callback.answer("✅ Категорію видалено")
    await _show_categories(callback, db_user)
