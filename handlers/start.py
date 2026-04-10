from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handlers.common import language_markup
from services.buttons import build_layout_markup
from services.context import AppContext
from services.texts import format_text, normalize_language
from services.users import get_user_by_telegram_id, get_user_language, set_user_language, touch_user, upsert_user
from utils.messages import answer_or_edit


def build_start_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="start")

    async def render_main(target: Message | CallbackQuery, language: str) -> None:
        async with app.session_factory() as session:
            title = await format_text(session, "user.main_title", language, fallback="Subnowa")
            body = await format_text(
                session,
                "user.main_body",
                language,
                fallback="Выберите раздел ниже.",
                ABOUT_URL=app.settings.about_url,
                REVIEW_URL=app.settings.review_url,
            )
            markup = await build_layout_markup(session, "main_menu", language)
        await answer_or_edit(target, f"<b>{title}</b>\n\n{body}", reply_markup=markup)

    async def notify_admins(text: str) -> None:
        for admin_id in app.settings.admin_ids:
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                continue

    @router.message(CommandStart())
    async def start_handler(message: Message, state: FSMContext) -> None:
        async with app.session_factory() as session:
            user, is_new = await upsert_user(
                session,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name or "",
                default_language=app.settings.default_language,
            )
            await touch_user(session, message.from_user.id)
            await session.commit()

        await state.clear()

        if is_new:
            await notify_admins(
                "Новый пользователь\n\n"
                f"ID: <code>{message.from_user.id}</code>\n"
                f"Username: @{message.from_user.username or 'нет'}"
            )

        if user.language_selected:
            await render_main(message, user.language.value)
            return

        async with app.session_factory() as session:
            text = await format_text(session, "user.choose_language", "ru", fallback="Выберите язык")
        await message.answer(f"<b>{text}</b>", reply_markup=language_markup())

    @router.callback_query(F.data == "menu:main")
    async def main_menu_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, default=app.settings.default_language)
            await touch_user(session, callback.from_user.id)
            await session.commit()
        await callback.answer()
        await render_main(callback, language)

    @router.callback_query(F.data == "menu:languages")
    async def open_languages_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, default=app.settings.default_language)
            text = await format_text(session, "user.choose_language", language, fallback="Выберите язык")
        await callback.answer()
        await answer_or_edit(callback, f"<b>{text}</b>", reply_markup=language_markup())

    @router.callback_query(F.data.startswith("lang:"))
    async def set_language_handler(callback: CallbackQuery, state: FSMContext) -> None:
        language = normalize_language(callback.data.split(":")[-1], app.settings.default_language)
        async with app.session_factory() as session:
            await upsert_user(
                session,
                telegram_id=callback.from_user.id,
                username=callback.from_user.username,
                full_name=callback.from_user.full_name or "",
                default_language=language,
            )
            await set_user_language(session, callback.from_user.id, language)
            await touch_user(session, callback.from_user.id)
            await session.commit()
        await state.clear()
        await callback.answer()
        await render_main(callback, language)

    @router.callback_query(F.data == "menu:faq")
    async def faq_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, default=app.settings.default_language)
            title = await format_text(session, "user.faq_title", language, fallback="FAQ")
            body = await format_text(session, "user.faq_body", language, fallback="FAQ")
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{title}</b>\n\n{body}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:main", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "noop")
    async def noop_handler(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.message()
    async def fallback_handler(message: Message) -> None:
        async with app.session_factory() as session:
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                await upsert_user(
                    session,
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    full_name=message.from_user.full_name or "",
                    default_language=app.settings.default_language,
                )
            await touch_user(session, message.from_user.id)
            language = await get_user_language(session, message.from_user.id, default=app.settings.default_language)
            await session.commit()
        await render_main(message, language)

    return router
