"""Мелкие помощники для инлайн-интерфейса бота."""
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto


def btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def kb(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def show(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None, photo=None) -> None:
    """Перерисовывает экран в том же сообщении, где нажали кнопку (с фото или без)."""
    msg = call.message
    try:
        if photo and msg.photo:
            await msg.edit_media(InputMediaPhoto(media=photo, caption=text), reply_markup=markup)
            return
        if not photo and msg.text:
            await msg.edit_text(text, reply_markup=markup)
            return
    except TelegramBadRequest as exc:
        if "not modified" in str(exc):
            return
    try:
        await msg.delete()
    except TelegramBadRequest:
        pass
    if photo:
        await msg.answer_photo(photo, caption=text, reply_markup=markup)
    else:
        await msg.answer(text, reply_markup=markup)
