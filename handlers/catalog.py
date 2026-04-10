from __future__ import annotations

from html import escape
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.base import OrderStatus
from handlers.common import (
    categories_markup,
    gmail_choice_markup,
    payment_methods_markup,
    product_markup,
    products_markup,
)
from services.capcut import count_free_accounts
from services.catalog import category_name, get_category, get_product, get_product_by_code, list_categories, list_category_products, render_product_text
from services.context import AppContext
from services.orders import attach_payment_method, change_status, create_custom_request, create_order, get_order_by_id, save_payment_proof
from services.payments import get_payment_method, list_product_payment_methods, payment_instruction
from services.settings import get_setting
from services.texts import format_text
from services.users import get_last_chatgpt_gmail, get_user_by_telegram_id, get_user_language, touch_user, user_has_trial
from states import UserFlowState
from utils.formatting import order_display_number, user_display_name
from utils.messages import answer_or_edit


GMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$", re.IGNORECASE)


def _back_text(language: str) -> str:
    return "◀ Назад" if language == "ru" else ("◀ Orqaga" if language == "uz" else "◀ Back")


def _menu_text(language: str) -> str:
    return "🏠 Меню" if language == "ru" else ("🏠 Menyu" if language == "uz" else "🏠 Menu")


def _subscription_markup(channel_url: str, callback_data: str, language: str) -> InlineKeyboardMarkup:
    subscribe = "Подписаться" if language == "ru" else ("Obuna bo'lish" if language == "uz" else "Subscribe")
    check = "Проверить подписку" if language == "ru" else ("Obunani tekshirish" if language == "uz" else "Check subscription")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subscribe, url=channel_url)],
            [InlineKeyboardButton(text=check, callback_data=callback_data)],
            [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
        ]
    )


def _is_valid_gmail(value: str) -> bool:
    return bool(GMAIL_PATTERN.match(value.strip()))


async def _notify_admins(bot: Bot, app: AppContext, text: str, order_id: int | None = None) -> None:
    markup = None
    if order_id:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ", callback_data=f"admin:order:{order_id}")]]
        )
    for admin_id in app.settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception:
            continue


async def _check_subscription(bot: Bot, channel: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel, user_id)
    except Exception:
        return False
    return getattr(member, "status", "") not in {"left", "kicked"}


def build_catalog_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="catalog")

    @router.callback_query(F.data == "menu:catalog")
    async def open_catalog_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            categories = await list_categories(session)
            title = await format_text(session, "user.catalog_title", language, fallback="Каталог")
            await touch_user(session, callback.from_user.id)
            await session.commit()
        await callback.answer()
        await answer_or_edit(callback, f"<b>{title}</b>", reply_markup=categories_markup(categories, language))

    @router.callback_query(F.data.startswith("catalog:back:"))
    async def catalog_back_handler(callback: CallbackQuery) -> None:
        await open_catalog_handler(callback)

    @router.callback_query(F.data.startswith("catalog:cat:"))
    async def category_handler(callback: CallbackQuery) -> None:
        category_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            category = await get_category(session, category_id)
            products = await list_category_products(session, category_id)
        await callback.answer()
        if category is None:
            await answer_or_edit(callback, "Категория не найдена.", reply_markup=None)
            return
        caption = f"<b>{category_name(category, language)}</b>"
        await answer_or_edit(callback, caption, reply_markup=products_markup(products, language, category_id))

    @router.callback_query(F.data.startswith("product:view:"))
    async def product_view_handler(callback: CallbackQuery) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product(session, product_id)
        await callback.answer()
        if product is None:
            await answer_or_edit(callback, "Товар не найден.")
            return
        include_trial = product.code == "chatgpt_plus_month"
        await answer_or_edit(
            callback,
            render_product_text(product, language),
            reply_markup=product_markup(product, language, include_trial=include_trial),
        )

    @router.callback_query(F.data == "product:trial")
    async def trial_entry_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "chatgpt_trial_3d")
            prompt = await format_text(session, "user.trial_gmail_prompt", language, fallback="Введите Gmail.")
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user and await user_has_trial(session, user.id):
                text = await format_text(session, "user.trial_already_used", language, fallback="Пробная подписка уже использована.")
                await callback.answer()
                await answer_or_edit(callback, text, reply_markup=product_markup(product, language, include_trial=True) if product else None)
                return
        await state.set_state(UserFlowState.waiting_trial_gmail)
        await state.update_data(product_id=product.id if product else None)
        await callback.answer()
        await answer_or_edit(callback, prompt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data="menu:catalog")]]))

    @router.message(UserFlowState.waiting_trial_gmail)
    async def trial_gmail_handler(message: Message, state: FSMContext) -> None:
        gmail = (message.text or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            if not _is_valid_gmail(gmail):
                await message.answer("Нужен корректный Gmail.")
                return
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
            prompt = await format_text(session, "user.trial_subscribe", language, fallback="Подпишитесь на канал.")
        channel_url = f"https://t.me/{required_channel.replace('@', '').strip()}"
        await state.update_data(gmail=gmail)
        await message.answer(
            prompt,
            reply_markup=_subscription_markup(channel_url, "trial:check", language),
        )

    @router.callback_query(F.data == "trial:check")
    async def trial_check_handler(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            product = await get_product_by_code(session, "chatgpt_trial_3d")
            if user is None or product is None:
                await callback.answer()
                return
            subscribed = await _check_subscription(bot, required_channel, callback.from_user.id)
            if not subscribed:
                text = await format_text(session, "user.trial_not_subscribed", language, fallback="Вы не подписаны на канал.")
                await callback.answer(text, show_alert=True)
                return
            order = await create_order(
                session,
                user=user,
                product=product,
                language=language,
                details={"gmail": data.get("gmail", "")},
                status=OrderStatus.PROCESSING,
            )
            await session.commit()
            created_text = await format_text(session, "user.trial_created", language, fallback="Пробная заявка создана.")
        await state.clear()
        await callback.answer()
        await answer_or_edit(callback, created_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")]]))
        await _notify_admins(
            bot,
            app,
            "Новая trial-заявка\n\n"
            f"Заказ: <code>{order_display_number(order)}</code>\n"
            f"Пользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\n"
            f"Gmail: {data.get('gmail', '-')}",
            order.id,
        )

    @router.callback_query(F.data.startswith("product:buy:"))
    async def product_buy_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product(session, product_id)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None or product is None:
                await callback.answer()
                return
            if product.workflow_type == "capcut_auto" and await count_free_accounts(session) <= 0:
                text = await format_text(session, "user.stock_empty", language, fallback="Склад пуст.")
                await callback.answer()
                await answer_or_edit(callback, text, reply_markup=product_markup(product, language))
                return
            if product.workflow_type == "chatgpt_manual":
                saved_gmail = await get_last_chatgpt_gmail(session, user.id)
                prompt = await format_text(session, "user.chatgpt_gmail_prompt", language, fallback="Введите Gmail.")
                if saved_gmail:
                    text = await format_text(session, "user.chatgpt_saved_gmail_choice", language, fallback="Использовать Gmail?", gmail=saved_gmail)
                    await state.update_data(product_id=product.id, saved_gmail=saved_gmail)
                    await callback.answer()
                    await answer_or_edit(callback, text, reply_markup=gmail_choice_markup(product.id, language))
                    return
                await state.set_state(UserFlowState.waiting_chatgpt_gmail)
                await state.update_data(product_id=product.id)
                await callback.answer()
                await answer_or_edit(callback, prompt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data=f"product:view:{product.id}")]]))
                return
            order = await create_order(session, user=user, product=product, language=language)
            methods = await list_product_payment_methods(session, product)
            payment_text = await format_text(session, "user.choose_payment_method", language, fallback="Выберите способ оплаты.")
            await session.commit()
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{order.product_name_snapshot}</b>\n\n{payment_text}",
            reply_markup=payment_methods_markup(order.id, methods, language),
        )
        await _notify_admins(
            bot,
            app,
            f"Новый заказ\n\nЗаказ: <code>{order_display_number(order)}</code>\nПользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\nТовар: {order.product_name_snapshot}",
            order.id,
        )

    @router.callback_query(F.data == "custom:open")
    async def custom_open_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.custom_request_prompt", language, fallback="Опишите, что вам нужно.")
        await state.set_state(UserFlowState.waiting_custom_request)
        await callback.answer()
        await answer_or_edit(callback, prompt)

    @router.message(UserFlowState.waiting_custom_request)
    async def custom_request_handler(message: Message, state: FSMContext) -> None:
        note = (message.text or "").strip()
        if not note:
            await message.answer("Нужно текстовое описание заявки.")
            return
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                await message.answer("Пользователь не найден.")
                return
            order = await create_custom_request(session, user=user, language=language, note=note)
            created_text = await format_text(session, "user.custom_request_created", language, fallback="Заявка создана.")
            await session.commit()
        await state.clear()
        await message.answer(created_text)
        await _notify_admins(
            bot,
            app,
            f"Новая кастомная заявка\n\nЗаказ: <code>{order_display_number(order)}</code>\nПользователь: <b>{escape(user_display_name(message.from_user, message.from_user.id))}</b>\nЗапрос: {escape(note)}",
            order.id,
        )

    @router.callback_query(F.data.startswith("chatgpt:saved:"))
    async def chatgpt_use_saved_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        data = await state.get_data()
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.trial_subscribe", language, fallback="Подпишитесь на канал.")
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
        await state.update_data(product_id=product_id, gmail=data.get("saved_gmail", ""))
        channel_url = f"https://t.me/{required_channel.replace('@', '').strip()}"
        await callback.answer()
        await answer_or_edit(callback, prompt, reply_markup=_subscription_markup(channel_url, "chatgpt:check", language))

    @router.callback_query(F.data.startswith("chatgpt:other:"))
    async def chatgpt_use_other_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.chatgpt_gmail_prompt", language, fallback="Введите Gmail.")
        await state.set_state(UserFlowState.waiting_chatgpt_gmail)
        await state.update_data(product_id=product_id)
        await callback.answer()
        await answer_or_edit(callback, prompt)

    @router.message(UserFlowState.waiting_chatgpt_gmail)
    async def chatgpt_gmail_handler(message: Message, state: FSMContext) -> None:
        gmail = (message.text or "").strip()
        if not _is_valid_gmail(gmail):
            await message.answer("Нужен корректный Gmail.")
            return
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.trial_subscribe", language, fallback="Подпишитесь на канал.")
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
        await state.update_data(gmail=gmail)
        channel_url = f"https://t.me/{required_channel.replace('@', '').strip()}"
        await message.answer(prompt, reply_markup=_subscription_markup(channel_url, "chatgpt:check", language))

    @router.callback_query(F.data == "chatgpt:check")
    async def chatgpt_check_handler(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        product_id = data.get("product_id")
        gmail = (data.get("gmail") or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
            subscribed = await _check_subscription(bot, required_channel, callback.from_user.id)
            if not subscribed:
                text = await format_text(session, "user.trial_not_subscribed", language, fallback="Вы не подписаны на канал.")
                await callback.answer(text, show_alert=True)
                return
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            product = await get_product(session, int(product_id)) if product_id else None
            if user is None or product is None:
                await callback.answer()
                return
            order = await create_order(session, user=user, product=product, language=language, details={"gmail": gmail})
            methods = await list_product_payment_methods(session, product)
            payment_text = await format_text(session, "user.choose_payment_method", language, fallback="Выберите способ оплаты.")
            await session.commit()
        await state.clear()
        await callback.answer()
        await answer_or_edit(callback, f"<b>{order.product_name_snapshot}</b>\n\n{payment_text}", reply_markup=payment_methods_markup(order.id, methods, language))
        await _notify_admins(
            bot,
            app,
            f"Новый заказ ChatGPT\n\nЗаказ: <code>{order_display_number(order)}</code>\nПользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\nGmail: {escape(gmail)}",
            order.id,
        )

    @router.callback_query(F.data.startswith("order:pay:"))
    async def order_payment_method_handler(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, order_id, payment_id = callback.data.split(":")
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            payment_method = await get_payment_method(session, int(payment_id))
            if order is None or payment_method is None:
                await callback.answer()
                return
            await attach_payment_method(session, order, payment_method)
            instruction = payment_instruction(payment_method, language)
            payment_prompt = await format_text(session, "user.send_payment_proof", language, fallback="После оплаты отправьте чек.")
            await session.commit()
        await state.set_state(UserFlowState.waiting_payment_proof)
        await state.update_data(order_id=int(order_id))
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{payment_method.admin_title}</b>\n\n{instruction}\n\n{payment_prompt}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Отмена", callback_data=f"order:cancel:{order_id}")],
                    [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
                ]
            ),
        )

    @router.callback_query(F.data.startswith("order:cancel:"))
    async def order_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        order_id = int(callback.data.split(":")[-1])
        order_reference = order_display_number(order_id)
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, order_id)
            if order is not None and order.user and order.user.telegram_id == callback.from_user.id and order.status != OrderStatus.COMPLETED:
                order_reference = order_display_number(order)
                await change_status(session, order, OrderStatus.CANCELLED, changed_by_telegram_id=callback.from_user.id)
                await session.commit()
            text = await format_text(session, "user.order_cancelled", language, fallback="Заказ отменён.", order_number=order_reference)
        await state.clear()
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")]]))

    @router.message(UserFlowState.waiting_payment_proof, F.photo)
    async def payment_photo_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        if not order_id:
            await message.answer("Заказ для чека не найден.")
            return
        file_id = message.photo[-1].file_id
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            if order is None:
                await message.answer("Заказ не найден.")
                return
            await save_payment_proof(session, order, file_id, "photo", changed_by_telegram_id=message.from_user.id)
            await session.commit()
            text = await format_text(session, "user.payment_check_saved", language, fallback="Чек получен.")
        await state.clear()
        await message.answer(text)
        for admin_id in app.settings.admin_ids:
            try:
                await bot.send_photo(
                    admin_id,
                    photo=file_id,
                    caption=(
                        "Новый чек\n\n"
                        f"Заказ: <code>{order_display_number(order)}</code>\n"
                        f"Пользователь: <b>{escape(user_display_name(message.from_user, message.from_user.id))}</b>\n"
                        f"Товар: {order.product_name_snapshot}"
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ", callback_data=f"admin:order:{order.id}")]]
                    ),
                )
            except Exception:
                continue

    @router.message(UserFlowState.waiting_payment_proof, F.document)
    async def payment_document_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        if not order_id:
            await message.answer("Заказ для чека не найден.")
            return
        file_id = message.document.file_id
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            if order is None:
                await message.answer("Заказ не найден.")
                return
            await save_payment_proof(session, order, file_id, "document", changed_by_telegram_id=message.from_user.id)
            await session.commit()
            text = await format_text(session, "user.payment_check_saved", language, fallback="Чек получен.")
        await state.clear()
        await message.answer(text)
        for admin_id in app.settings.admin_ids:
            try:
                await bot.send_document(
                    admin_id,
                    document=file_id,
                    caption=(
                        "Новый чек\n\n"
                        f"Заказ: <code>{order_display_number(order)}</code>\n"
                        f"Пользователь: <b>{escape(user_display_name(message.from_user, message.from_user.id))}</b>\n"
                        f"Товар: {order.product_name_snapshot}"
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ", callback_data=f"admin:order:{order.id}")]]
                    ),
                )
            except Exception:
                continue

    @router.message(UserFlowState.waiting_payment_proof)
    async def payment_invalid_proof_handler(message: Message) -> None:
        await message.answer("Отправьте чек фотографией или документом.")

    return router
