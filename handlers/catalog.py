from __future__ import annotations

from html import escape
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery

from db.base import OrderStatus
from handlers.common import (
    categories_markup,
    gmail_choice_markup,
    profile_markup,
    product_markup,
    products_markup,
)
from services.capcut import count_free_accounts
from services.catalog import category_name, get_category, get_product, get_product_by_code, list_categories, list_category_products, render_product_text
from services.context import AppContext
from services.order_processing import mark_order_paid
from services.orders import (
    change_status,
    create_custom_request,
    create_order,
    get_order_by_id,
    get_order_by_number,
    store_checkout_message_ref,
    update_payment_meta,
)
from services.settings import get_setting
from services.telegram_payments import (
    can_pay_order,
    invalid_order_text,
    invoice_total_amount,
    payment_provider_name,
    payment_unavailable_text,
    pre_checkout_error_text,
    provider_token_enabled,
    send_order_invoice,
)
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
            [InlineKeyboardButton(text=check, callback_data=callback_data, style="success")],
            [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
        ]
    )


def _is_valid_gmail(value: str) -> bool:
    return bool(GMAIL_PATTERN.match(value.strip()))


def _rate_error_text(language: str) -> str:
    if language == "uz":
        return "USD kursini olib bo'lmadi. Iltimos, birozdan keyin qayta urinib ko'ring."
    if language == "en":
        return "Could not fetch the USD exchange rate right now. Please try again in a moment."
    return "Сейчас не удалось получить курс USD. Пожалуйста, попробуйте ещё раз через минуту."


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

    async def _send_text(target: CallbackQuery | Message, text: str) -> None:
        if isinstance(target, CallbackQuery):
            await answer_or_edit(target, text)
            return
        await target.answer(text)

    async def _send_invoice_for_order(
        target: CallbackQuery | Message,
        session,
        order,
        language: str,
    ) -> bool:
        if not provider_token_enabled(app.settings):
            await _send_text(target, payment_unavailable_text(language))
            return False
        if not can_pay_order(order):
            await _send_text(target, invalid_order_text(language))
            return False
        try:
            invoice_message = await send_order_invoice(
                bot,
                app.settings,
                order,
                chat_id=target.from_user.id,
                language=language,
            )
        except Exception:
            await _send_text(target, payment_unavailable_text(language))
            return False

        await update_payment_meta(
            session,
            order,
            payment_provider=payment_provider_name(),
            payment_status="invoice_sent",
            invoice_id=order.order_number,
        )
        await store_checkout_message_ref(
            session,
            order,
            chat_id=invoice_message.chat.id,
            message_id=invoice_message.message_id,
        )
        await session.commit()
        return True

    def _manual_payment_removed_text(language: str) -> str:
        if language == "uz":
            return "To'lov endi faqat Telegram ichidagi invoice orqali o'tadi. Buyurtmani qayta ochib invoice yuborilgan xabardan to'lang."
        if language == "en":
            return "Payment now works only through the Telegram invoice. Open the order again and pay from the invoice message."
        return "Оплата теперь проходит только через Telegram invoice. Откройте заказ заново и оплатите из сообщения со счётом."

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
            reply_markup=product_markup(product, language, include_trial=include_trial, support_url=app.settings.support_url),
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
                await answer_or_edit(
                    callback,
                    text,
                    reply_markup=product_markup(product, language, include_trial=True, support_url=app.settings.support_url) if product else None,
                )
                return
        await state.set_state(UserFlowState.waiting_trial_gmail)
        await state.update_data(product_id=product.id if product else None)
        await callback.answer()
        await answer_or_edit(
            callback,
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data="menu:catalog", style="danger")]]
            ),
        )

    @router.message(UserFlowState.waiting_trial_gmail)
    async def trial_gmail_handler(message: Message, state: FSMContext) -> None:
        gmail = (message.text or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            if not _is_valid_gmail(gmail):
                invalid_text = await format_text(session, "user.invalid_gmail", language, fallback="Введите корректный Gmail в формате name@gmail.com.")
                await message.answer(invalid_text)
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
                await answer_or_edit(
                    callback,
                    text,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text=_menu_text(language), callback_data="menu:main")],
                            [InlineKeyboardButton(text="💬 Задать вопрос" if language == "ru" else ("💬 Savol berish" if language == "uz" else "💬 Support"), url=app.settings.support_url)],
                        ]
                    ),
                )
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
                await answer_or_edit(
                    callback,
                    prompt,
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data=f"product:view:{product.id}", style="danger")]]
                    ),
                )
                return
            order = await create_order(session, user=user, product=product, language=language)
            await session.commit()
            await state.clear()
            await callback.answer()
            if not await _send_invoice_for_order(callback, session, order, language):
                return
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
        await answer_or_edit(
            callback,
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=_back_text(language), callback_data=f"product:view:{product_id}", style="danger")]]
            ),
        )

    @router.message(UserFlowState.waiting_chatgpt_gmail)
    async def chatgpt_gmail_handler(message: Message, state: FSMContext) -> None:
        gmail = (message.text or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            if not _is_valid_gmail(gmail):
                invalid_text = await format_text(session, "user.invalid_gmail", language, fallback="Введите корректный Gmail в формате name@gmail.com.")
                await message.answer(invalid_text)
                return
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
            await session.commit()
            await state.clear()
            await callback.answer()
            if not await _send_invoice_for_order(callback, session, order, language):
                return
        await _notify_admins(
            bot,
            app,
            f"Новый заказ ChatGPT\n\nЗаказ: <code>{order_display_number(order)}</code>\nПользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\nGmail: {escape(gmail)}",
            order.id,
        )

    @router.callback_query(F.data.startswith("order:payment_methods:"))
    async def order_payment_methods_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, order_id)
            if order is None or order.product is None:
                await callback.answer()
                return
            await callback.answer()
            await _send_invoice_for_order(callback, session, order, language)

    @router.callback_query(F.data.startswith("order:promo:"))
    async def order_promo_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            await state.clear()
            await callback.answer()
            await _send_invoice_for_order(callback, session, order, language)

    @router.message(UserFlowState.waiting_promo_code)
    async def promo_code_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        return_to = data.get("promo_return", "profile")
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            invalid_text = await format_text(session, "user.promo_invalid", language, fallback="К сожалению, такого промокода не существует.")
            await state.clear()
            await message.answer(invalid_text)
            if return_to == "profile":
                title = await format_text(session, "user.profile_title", language, fallback="Ваш профиль")
                display_name = escape(user_display_name(message.from_user, message.from_user.id))
                await message.answer(
                    f"<b>{title}</b>\n\nПользователь: <b>{display_name}</b>\nID: <code>{message.from_user.id}</code>",
                    reply_markup=profile_markup(language, app.settings.support_url),
                )
                return
            if isinstance(return_to, str) and return_to.startswith("payment:"):
                order_id = int(return_to.split(":")[-1])
                order = await get_order_by_id(session, order_id)
                if order is None or order.product is None:
                    return
                await _send_invoice_for_order(message, session, order, language)
                return

    @router.callback_query(F.data.startswith("order:pay:"))
    async def order_payment_method_handler(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, order_id, _payment_id = callback.data.split(":")
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            if order is None:
                await callback.answer()
                return
            await state.clear()
            await callback.answer()
            await _send_invoice_for_order(callback, session, order, language)

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
        await state.clear()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id)) if order_id else None
        if order is None:
            await message.answer(_manual_payment_removed_text(language))
            return
        async with app.session_factory() as session:
            order = await get_order_by_id(session, int(order_id)) if order_id else None
            if order is None:
                await message.answer(_manual_payment_removed_text(language))
                return
            await _send_invoice_for_order(message, session, order, language)

    @router.message(UserFlowState.waiting_payment_proof, F.document)
    async def payment_document_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        await state.clear()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id)) if order_id else None
        if order is None:
            await message.answer(_manual_payment_removed_text(language))
            return
        async with app.session_factory() as session:
            order = await get_order_by_id(session, int(order_id)) if order_id else None
            if order is None:
                await message.answer(_manual_payment_removed_text(language))
                return
            await _send_invoice_for_order(message, session, order, language)

    @router.message(UserFlowState.waiting_payment_proof)
    async def payment_invalid_proof_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        await state.clear()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id)) if order_id else None
        if order is None:
            await message.answer(_manual_payment_removed_text(language))
            return
        async with app.session_factory() as session:
            order = await get_order_by_id(session, int(order_id)) if order_id else None
            if order is None:
                await message.answer(_manual_payment_removed_text(language))
                return
            await _send_invoice_for_order(message, session, order, language)

    @router.pre_checkout_query()
    async def pre_checkout_handler(query: PreCheckoutQuery) -> None:
        async with app.session_factory() as session:
            order = await get_order_by_number(session, query.invoice_payload)
            language = order.language if order is not None else app.settings.default_language
            if order is None:
                await query.answer(ok=False, error_message=pre_checkout_error_text(language))
                return
            if not can_pay_order(order):
                await query.answer(ok=False, error_message=invalid_order_text(language))
                return
            if query.currency != order.currency or query.total_amount != invoice_total_amount(order):
                await query.answer(ok=False, error_message=pre_checkout_error_text(language))
                return
        await query.answer(ok=True)

    @router.message(F.successful_payment)
    async def successful_payment_handler(message: Message) -> None:
        payment = message.successful_payment
        if payment is None:
            return

        async with app.session_factory() as session:
            order = await get_order_by_number(session, payment.invoice_payload)
            if order is None:
                await message.answer(pre_checkout_error_text(app.settings.default_language))
                return
            if payment.currency != order.currency or payment.total_amount != invoice_total_amount(order):
                await message.answer(pre_checkout_error_text(order.language or app.settings.default_language))
                return

            await update_payment_meta(
                session,
                order,
                payment_provider=payment_provider_name(),
                payment_status="paid",
                invoice_id=payment.telegram_payment_charge_id,
                invoice_uuid=payment.provider_payment_charge_id,
            )
            await mark_order_paid(
                session,
                bot,
                app.settings,
                order,
                note="telegram_payments:successful_payment",
            )
            await session.commit()

    return router
