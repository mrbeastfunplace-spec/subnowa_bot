from __future__ import annotations

from aiogram.types import CallbackQuery, Message


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
        except Exception:
            await message.answer(text=text, reply_markup=reply_markup)
        return

    await target.answer(text=text, reply_markup=reply_markup)
