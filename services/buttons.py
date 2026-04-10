from __future__ import annotations

from collections import defaultdict

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import ButtonActionType
from db.models import Layout, LayoutButton
from utils.translations import pick_translation


def button_text(button: LayoutButton, language: str) -> str:
    return pick_translation(button.translations, language, "text") or button.code


async def get_layout(session: AsyncSession, code: str) -> Layout | None:
    return await session.scalar(select(Layout).where(Layout.code == code, Layout.is_active.is_(True)))


async def list_layouts(session: AsyncSession) -> list[Layout]:
    result = await session.scalars(select(Layout).order_by(Layout.scope, Layout.title, Layout.id))
    return list(result.all())


async def get_button(session: AsyncSession, button_id: int) -> LayoutButton | None:
    return await session.scalar(select(LayoutButton).where(LayoutButton.id == button_id))


async def build_layout_markup(
    session: AsyncSession,
    layout_code: str,
    language: str,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> InlineKeyboardMarkup:
    layout = await get_layout(session, layout_code)
    rows: list[list[InlineKeyboardButton]] = []
    if layout is not None:
        grouped: dict[int, list[InlineKeyboardButton]] = defaultdict(list)
        buttons = sorted(
            [button for button in layout.buttons if button.is_active],
            key=lambda item: (item.row_index, item.sort_order, item.id),
        )
        for button in buttons:
            text = button_text(button, language)
            button_kwargs = {}
            if button.style and button.style != "default":
                button_kwargs["style"] = button.style
            if button.action_type == ButtonActionType.URL:
                grouped[button.row_index].append(InlineKeyboardButton(text=text, url=button.action_value, **button_kwargs))
            else:
                grouped[button.row_index].append(InlineKeyboardButton(text=text, callback_data=button.action_value, **button_kwargs))
        rows.extend(grouped[index] for index in sorted(grouped))
    if extra_rows:
        rows.extend(extra_rows)
    return InlineKeyboardMarkup(inline_keyboard=rows)
