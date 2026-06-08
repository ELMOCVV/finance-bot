from aiogram.fsm.context import FSMContext
from aiogram.types import Message

HOST_MID_KEY = "_host_mid"


async def edit_host(message: Message, state: FSMContext, text: str, reply_markup=None) -> None:
    """Edit the FSM host message in-place rather than sending a new one."""
    data = await state.get_data()
    mid = data.get(HOST_MID_KEY)
    if mid:
        try:
            await message.bot.edit_message_text(
                text,
                chat_id=message.chat.id,
                message_id=mid,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return
        except Exception:
            pass
    await message.answer(text, reply_markup=reply_markup)


async def get_host_mid(state: FSMContext) -> int | None:
    data = await state.get_data()
    return data.get(HOST_MID_KEY)
