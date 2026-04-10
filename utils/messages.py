from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message


def _strip_button_styles(reply_markup):
    if not isinstance(reply_markup, InlineKeyboardMarkup):
        return reply_markup

    rows: list[list[InlineKeyboardButton]] = []
    for row in reply_markup.inline_keyboard:
        normalized_row: list[InlineKeyboardButton] = []
        for button in row:
            payload = button.model_dump(exclude_none=True)
            payload.pop("style", None)
            normalized_row.append(InlineKeyboardButton(**payload))
        rows.append(normalized_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _safe_send_message(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.answer(text=text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "DOCUMENT_INVALID" not in str(exc):
            raise
        await message.answer(text=text, reply_markup=_strip_button_styles(reply_markup))


async def answer_or_edit(target: Message | CallbackQuery, text: str, reply_markup=None) -> None:
    if isinstance(target, CallbackQuery):
        message = target.message
        if message is None:
            return
        try:
            if message.photo or message.document:
                await message.edit_caption(caption=text, reply_markup=reply_markup)
            else:
                await message.edit_text(text=text, reply_markup=reply_markup)
        except TelegramBadRequest as exc:
            if "DOCUMENT_INVALID" in str(exc):
                await _safe_send_message(message, text, reply_markup)
            else:
                await message.answer(text=text, reply_markup=reply_markup)
        except Exception:
            await message.answer(text=text, reply_markup=reply_markup)
        return

    await _safe_send_message(target, text, reply_markup)
