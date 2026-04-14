from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.base import OrderStatus
from handlers.common import profile_markup
from services.capcut import count_free_accounts
from services.catalog import get_product, get_product_by_code
from services.checkout import build_checkout_link_markup, build_order_card_text
from services.context import AppContext
from services.legacy_ui import (
    build_capcut_menu_markup,
    build_details_markup,
    build_gmail_choice_markup,
    build_menu_only_markup,
    build_other_menu_markup,
    build_single_back_markup,
    build_stock_empty_markup,
    build_subscription_check_markup,
    build_subscriptions_markup,
    build_chatgpt_menu_markup,
    capcut_card_text,
    chatgpt_card_text,
    multi_service_name,
    other_request_name,
    product_title,
    text as ui_text,
)
from services.multicard import MulticardError, convert_uzs_to_usd, create_invoice
from services.orders import change_status, create_custom_request, create_order, get_order_by_id, update_payment_meta
from services.settings import get_setting
from services.users import get_last_chatgpt_gmail, get_user_by_telegram_id, get_user_language, touch_user, user_has_trial
from states import UserFlowState
from utils.formatting import user_display_name
from utils.messages import answer_or_edit


GMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$", re.IGNORECASE)
logger = logging.getLogger(__name__)


def _is_valid_gmail(value: str) -> bool:
    return bool(GMAIL_PATTERN.match(value.strip()))


async def _check_subscription(bot: Bot, channel: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel, user_id)
    except Exception:
        return False
    return getattr(member, "status", "") not in {"left", "kicked"}


def _admin_order_markup(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ", callback_data=f"admin:order:{order_id}")]]
    )


async def _notify_admins(bot: Bot, app: AppContext, text: str, order_id: int | None = None) -> None:
    markup = _admin_order_markup(order_id) if order_id else None
    for admin_id in app.settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception:
            continue


def _append_query(url: str, **params: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value})
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def _invoice_active(order) -> bool:
    if not order.checkout_url or not order.invoice_expiry_at:
        return False
    expiry_at = order.invoice_expiry_at
    if expiry_at.tzinfo is None:
        expiry_at = expiry_at.replace(tzinfo=timezone.utc)
    return expiry_at > datetime.now(timezone.utc)


def _invoice_error_text(language: str) -> str:
    if language == "uz":
        return "Multicard invoice yaratib bo'lmadi. Iltimos, keyinroq qayta urinib ko'ring."
    if language == "en":
        return "Unable to create a Multicard invoice right now. Please try again a bit later."
    return "Не удалось создать счёт Multicard. Пожалуйста, попробуйте ещё раз чуть позже."


def _checkout_redirect_text(language: str) -> str:
    if language == "uz":
        return "To'lov endi Multicard checkout orqali amalga oshiriladi. Quyida amal qiluvchi to'lov havolasini yubordim."
    if language == "en":
        return "Payments now go through Multicard checkout. I sent the active payment link below."
    return "Оплата теперь проходит через Multicard checkout. Ниже отправил актуальную ссылку на оплату."


def build_catalog_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="legacy_catalog")

    async def _show_subscriptions(target: CallbackQuery, language: str) -> None:
        await answer_or_edit(
            target,
            f"<b>{ui_text(language, 'subscriptions_title')}</b>",
            reply_markup=build_subscriptions_markup(language),
        )

    async def _prepare_checkout_card(order_id: int, language: str):
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                return None
            try:
                price_usd = await convert_uzs_to_usd(order.amount)
            except Exception:
                return "error", None
            checkout_url = (order.checkout_url or "").strip()
            if not _invoice_active(order) or order.payment_status == "failed" or not checkout_url:
                try:
                    invoice = await create_invoice(
                        app.settings,
                        amount_uzs=order.amount,
                        invoice_id=order.order_number,
                        language=language,
                        callback_url=_append_query(app.settings.multicard_callback_url, order=order.order_number),
                        return_url=_append_query(app.settings.multicard_return_url, order=order.order_number),
                    )
                except MulticardError as exc:
                    logger.exception("Failed to create Multicard invoice for order %s: %s", order.order_number, exc)
                    return "error", None
                await update_payment_meta(
                    session,
                    order,
                    payment_provider="multicard",
                    payment_status="",
                    invoice_id=invoice.invoice_id,
                    invoice_uuid=invoice.uuid,
                    checkout_url=invoice.checkout_url,
                    invoice_expiry_at=invoice.expiry_at,
                )
                await session.commit()
                checkout_url = invoice.checkout_url.strip()
            if not checkout_url:
                return "error", None
            return (
                build_order_card_text(order, language, price_usd),
                build_checkout_link_markup(checkout_url, language),
            )

    async def _show_invoice(callback: CallbackQuery, order, language: str) -> None:
        presentation = await _prepare_checkout_card(order.id, language)
        if presentation is None:
            await answer_or_edit(callback, "Заказ не найден.")
            return
        if presentation[0] == "error":
            if callback.message is not None:
                await callback.message.answer(_invoice_error_text(language))
            else:
                await answer_or_edit(callback, _invoice_error_text(language))
            return
        text, markup = presentation
        await answer_or_edit(callback, text, reply_markup=markup)

    async def _send_invoice_message(message: Message, order_id: int, language: str) -> None:
        presentation = await _prepare_checkout_card(order_id, language)
        if presentation is None:
            await message.answer("Заказ не найден.")
            return
        if presentation[0] == "error":
            await message.answer(_invoice_error_text(language))
            return
        text, markup = presentation
        await message.answer(text, reply_markup=markup)

    async def _redirect_to_checkout(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        order_id = data.get("order_id")
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id)) if order_id else None
        await state.clear()
        await message.answer(_checkout_redirect_text(language))
        if order_id and order is None:
            await message.answer("Заказ не найден.")
            return
        if order is not None:
            await _send_invoice_message(message, order.id, language)

    @router.callback_query(F.data.in_({"menu:catalog", "open_subscriptions"}))
    async def open_catalog_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            await touch_user(session, callback.from_user.id)
            await session.commit()
        await state.clear()
        await callback.answer()
        await _show_subscriptions(callback, language)

    @router.callback_query(F.data.startswith("catalog:back:"))
    async def catalog_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await open_catalog_handler(callback, state)

    @router.callback_query(F.data == "open_grok")
    async def open_grok_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await callback.answer(ui_text(language, "grok_unavailable"), show_alert=True)

    @router.callback_query(F.data.in_({"open_other", "custom:open"}))
    async def open_other_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "custom_text"),
            reply_markup=build_other_menu_markup(language),
        )

    @router.callback_query(F.data.in_({"other_adobe", "other_games", "other_telegram", "other_yandex", "other_music", "other_custom_own"}))
    async def other_request_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            request_name = other_request_name(language, callback.data)
            if user is None or not request_name:
                await callback.answer()
                return
            order = await create_custom_request(session, user=user, language=language, note=request_name)
            order.product_name_snapshot = request_name
            await session.commit()
        await state.clear()
        await callback.answer()
        await answer_or_edit(callback, ui_text(language, "custom_sent"), reply_markup=build_menu_only_markup(language))
        await _notify_admins(
            bot,
            app,
            "Новая заявка из раздела «Другое»\n\n"
            f"Пользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\n"
            f"Username: @{callback.from_user.username or 'нет'}\n"
            f"ID: <code>{callback.from_user.id}</code>\n"
            f"Запрос: {escape(request_name)}",
            order.id,
        )

    @router.callback_query(F.data == "open_chatgpt")
    async def open_chatgpt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "chatgpt_plus_month")
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "chatgpt_menu_text"),
            reply_markup=build_chatgpt_menu_markup(language, app.settings.support_url, product.price if product else 99000),
        )

    @router.callback_query(F.data == "open_capcut")
    async def open_capcut_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "capcut_pro_month")
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "capcut_menu_text"),
            reply_markup=build_capcut_menu_markup(language, app.settings.support_url, product.price if product else 49000),
        )

    @router.callback_query(F.data == "capcut_locked")
    async def capcut_locked_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await callback.answer(ui_text(language, "capcut_locked"), show_alert=True)

    @router.callback_query(F.data == "chatgpt_1m")
    async def chatgpt_1m_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "chatgpt_plus_month")
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            chatgpt_card_text(language, product.price if product else 99000),
            reply_markup=build_details_markup(language, "chatgpt_1m"),
        )

    @router.callback_query(F.data == "capcut_1m")
    async def capcut_1m_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "capcut_pro_month")
            free_count = await count_free_accounts(session)
        await state.clear()
        await callback.answer()
        if free_count <= 0:
            await answer_or_edit(
                callback,
                ui_text(language, "stock_empty"),
                reply_markup=build_stock_empty_markup(language, app.settings.support_url),
            )
            return
        await answer_or_edit(
            callback,
            capcut_card_text(language, product.price if product else 49000),
            reply_markup=build_details_markup(language, "capcut_1m"),
        )

    @router.callback_query(F.data == "back_to_chatgpt_1m")
    async def back_to_chatgpt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await open_chatgpt_handler(callback, state)

    @router.callback_query(F.data == "back_to_capcut_1m")
    async def back_to_capcut_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await open_capcut_handler(callback, state)

    @router.callback_query(F.data.in_({"multi_chatgpt", "multi_capcut"}))
    async def multi_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.set_state(UserFlowState.waiting_multi_quantity)
        await state.update_data(service_name=multi_service_name(language, callback.data))
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "multi_quantity"),
            reply_markup=build_single_back_markup(language, "open_subscriptions"),
        )

    @router.message(UserFlowState.waiting_multi_quantity)
    async def multi_quantity_handler(message: Message, state: FSMContext) -> None:
        quantity_value = (message.text or "").strip()
        if not quantity_value.isdigit():
            await message.answer("Введите число.")
            return
        quantity = int(quantity_value)
        if quantity <= 0:
            await message.answer("Введите число больше нуля.")
            return
        data = await state.get_data()
        service_name = data.get("service_name") or "Unknown"
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                await message.answer("Пользователь не найден.")
                return
            order = await create_custom_request(session, user=user, language=language, note=f"{service_name} x {quantity}")
            order.product_name_snapshot = f"{service_name} x {quantity}"
            await session.commit()
        await state.clear()
        await message.answer(ui_text(language, "multi_done"))
        await _notify_admins(
            bot,
            app,
            "Новая заявка «Хочу несколько»\n\n"
            f"Пользователь: <b>{escape(user_display_name(message.from_user, message.from_user.id))}</b>\n"
            f"Username: @{message.from_user.username or 'нет'}\n"
            f"ID: <code>{message.from_user.id}</code>\n"
            f"Сервис: {escape(service_name)}\n"
            f"Количество: {quantity}",
            order.id,
        )

    @router.callback_query(F.data == "chatgpt_trial")
    async def chatgpt_trial_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user and await user_has_trial(session, user.id):
                await callback.answer(ui_text(language, "trial_already_used"), show_alert=True)
                return
        await state.set_state(UserFlowState.waiting_trial_name)
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "trial_name"),
            reply_markup=build_single_back_markup(language, "open_chatgpt"),
        )

    @router.message(UserFlowState.waiting_trial_name)
    async def trial_name_handler(message: Message, state: FSMContext) -> None:
        full_name = (message.text or "").strip()
        if not full_name:
            await message.answer("Введите имя.")
            return
        await state.update_data(trial_name=full_name)
        await state.set_state(UserFlowState.waiting_trial_phone)
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        await message.answer(ui_text(language, "trial_phone"))

    @router.message(UserFlowState.waiting_trial_phone)
    async def trial_phone_handler(message: Message, state: FSMContext) -> None:
        phone = (message.text or "").strip()
        if not phone:
            await message.answer("Введите номер телефона.")
            return
        await state.update_data(trial_phone=phone)
        await state.set_state(UserFlowState.waiting_trial_gmail)
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        await message.answer(ui_text(language, "trial_gmail"))

    @router.message(UserFlowState.waiting_trial_gmail)
    async def trial_gmail_handler(message: Message, state: FSMContext) -> None:
        gmail = (message.text or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            if not _is_valid_gmail(gmail):
                await message.answer(ui_text(language, "invalid_gmail"))
                return
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
        await state.update_data(trial_gmail=gmail)
        await message.answer(
            ui_text(language, "trial_subscribe"),
            reply_markup=build_subscription_check_markup(language, required_channel, "trial:check"),
        )

    @router.callback_query(F.data == "trial:check")
    async def trial_check_handler(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
            subscribed = await _check_subscription(bot, required_channel, callback.from_user.id)
            if not subscribed:
                await callback.answer()
                await callback.message.answer(ui_text(language, "trial_not_subscribed"))
                return
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            product = await get_product_by_code(session, "chatgpt_trial_3d")
            if user is None or product is None:
                await callback.answer()
                return
            order = await create_order(
                session,
                user=user,
                product=product,
                language=language,
                details={
                    "gmail": (data.get("trial_gmail") or "").strip(),
                    "full_name": (data.get("trial_name") or "").strip(),
                    "phone": (data.get("trial_phone") or "").strip(),
                },
                status=OrderStatus.PROCESSING,
            )
            order.product_name_snapshot = product_title(language, product.code)
            await session.commit()
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "trial_created", order_number=order.order_number),
            reply_markup=build_menu_only_markup(language),
        )
        await _notify_admins(
            bot,
            app,
            "Новая заявка на 3 дня бесплатно\n\n"
            f"Пользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\n"
            f"Username: @{callback.from_user.username or 'нет'}\n"
            f"ID: <code>{callback.from_user.id}</code>\n"
            f"Заказ: {order.order_number}\n"
            f"Gmail: {escape((data.get('trial_gmail') or '').strip())}\n"
            f"Телефон: {escape((data.get('trial_phone') or '').strip())}",
            order.id,
        )

    @router.callback_query(F.data == "buy_chatgpt_1m")
    async def buy_chatgpt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            product = await get_product_by_code(session, "chatgpt_plus_month")
            if user is None or product is None:
                await callback.answer()
                return
            saved_gmail = await get_last_chatgpt_gmail(session, user.id)
        if saved_gmail:
            await state.set_state(UserFlowState.waiting_chatgpt_gmail_choice)
            await state.update_data(product_code="chatgpt_plus_month", saved_gmail=saved_gmail)
            await callback.answer()
            await answer_or_edit(
                callback,
                ui_text(language, "chatgpt_month_gmail_choice", gmail=escape(saved_gmail)),
                reply_markup=build_gmail_choice_markup(language),
            )
            return
        await state.set_state(UserFlowState.waiting_chatgpt_gmail)
        await state.update_data(product_code="chatgpt_plus_month")
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "chatgpt_month_gmail"),
            reply_markup=build_single_back_markup(language, "chatgpt_1m"),
        )

    @router.callback_query(F.data == "chatgpt_month_use_saved_gmail")
    async def chatgpt_use_saved_handler(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        saved_gmail = (data.get("saved_gmail") or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
        if not saved_gmail:
            await state.set_state(UserFlowState.waiting_chatgpt_gmail)
            await callback.answer()
            await answer_or_edit(
                callback,
                ui_text(language, "chatgpt_month_gmail"),
                reply_markup=build_single_back_markup(language, "chatgpt_1m"),
            )
            return
        await state.update_data(gmail=saved_gmail)
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "chatgpt_month_selected_gmail", gmail=escape(saved_gmail)),
            reply_markup=build_subscription_check_markup(language, required_channel, "chatgpt:check"),
        )

    @router.callback_query(F.data == "chatgpt_month_use_other_gmail")
    async def chatgpt_use_other_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.set_state(UserFlowState.waiting_chatgpt_gmail)
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "chatgpt_month_gmail"),
            reply_markup=build_single_back_markup(language, "chatgpt_1m"),
        )

    @router.message(UserFlowState.waiting_chatgpt_gmail)
    async def chatgpt_gmail_handler(message: Message, state: FSMContext) -> None:
        gmail = (message.text or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            if not _is_valid_gmail(gmail):
                await message.answer(ui_text(language, "invalid_gmail"))
                return
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
        await state.update_data(gmail=gmail)
        await message.answer(
            ui_text(language, "chatgpt_month_subscribe"),
            reply_markup=build_subscription_check_markup(language, required_channel, "chatgpt:check"),
        )

    @router.callback_query(F.data == "chatgpt:check")
    async def chatgpt_check_handler(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        gmail = (data.get("gmail") or "").strip()
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            required_channel = await get_setting(session, "required_channel", app.settings.required_channel)
            subscribed = await _check_subscription(bot, required_channel, callback.from_user.id)
            if not subscribed:
                await callback.answer()
                await callback.message.answer(ui_text(language, "chatgpt_month_not_subscribed"))
                return
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            product = await get_product_by_code(session, "chatgpt_plus_month")
            if user is None or product is None or not gmail:
                await callback.answer()
                return
            order = await create_order(session, user=user, product=product, language=language, details={"gmail": gmail})
            order.product_name_snapshot = product_title(language, product.code)
            await session.commit()
        await state.clear()
        await callback.answer()
        await _show_invoice(callback, order, language)
        await _notify_admins(
            bot,
            app,
            "Новая заявка ChatGPT Plus 1 месяц\n\n"
            f"Пользователь: <b>{escape(user_display_name(callback.from_user, callback.from_user.id))}</b>\n"
            f"Username: @{callback.from_user.username or 'нет'}\n"
            f"ID: <code>{callback.from_user.id}</code>\n"
            f"Заказ: {order.order_number}\n"
            f"Gmail: {escape(gmail)}",
            order.id,
        )

    @router.callback_query(F.data == "buy_capcut_1m")
    async def buy_capcut_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            product = await get_product_by_code(session, "capcut_pro_month")
            free_count = await count_free_accounts(session)
            if user is None or product is None:
                await callback.answer()
                return
            if free_count <= 0:
                await callback.answer()
                await answer_or_edit(
                    callback,
                    ui_text(language, "stock_empty"),
                    reply_markup=build_stock_empty_markup(language, app.settings.support_url),
                )
                return
            order = await create_order(session, user=user, product=product, language=language)
            order.product_name_snapshot = product_title(language, product.code)
            await session.commit()
        await state.clear()
        await callback.answer()
        await _show_invoice(callback, order, language)

    @router.callback_query(F.data.startswith("product:view:"))
    async def legacy_product_view_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
        if product is None:
            await callback.answer()
            return
        if product.code == "chatgpt_plus_month":
            await chatgpt_1m_handler(callback, state)
            return
        if product.code == "capcut_pro_month":
            await capcut_1m_handler(callback, state)
            return
        await open_catalog_handler(callback, state)

    @router.callback_query(F.data == "product:trial")
    async def legacy_trial_alias_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await chatgpt_trial_handler(callback, state)

    @router.callback_query(F.data.startswith("product:buy:"))
    async def legacy_product_buy_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
        if product is None:
            await callback.answer()
            return
        if product.code == "chatgpt_plus_month":
            await buy_chatgpt_handler(callback, state)
            return
        if product.code == "capcut_pro_month":
            await buy_capcut_handler(callback, state)
            return
        await callback.answer()

    @router.callback_query(F.data.startswith("order:payment_methods:"))
    async def order_payment_methods_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
        await callback.answer()
        await _show_invoice(callback, order, language)

    @router.callback_query(F.data.startswith("order:promo:"))
    async def order_promo_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.set_state(UserFlowState.waiting_promo_code)
        await state.update_data(promo_return=f"payment:{order_id}")
        await callback.answer()
        await answer_or_edit(
            callback,
            "Введите промокод.",
            reply_markup=build_single_back_markup(language, f"order:payment_methods:{order_id}"),
        )

    @router.message(UserFlowState.waiting_promo_code)
    async def promo_code_handler(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        return_to = data.get("promo_return", "profile")
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            await state.clear()
        await message.answer("К сожалению, такого промокода не существует.")
        if return_to == "profile":
            display_name = escape(user_display_name(message.from_user, message.from_user.id))
            await message.answer(
                "<b>Ваш профиль\n\nВыберите раздел 👇</b>\n\n"
                f"Пользователь: <b>{display_name}</b>\nID: <code>{message.from_user.id}</code>",
                reply_markup=profile_markup(language, app.settings.support_url),
            )
            return
        if isinstance(return_to, str) and return_to.startswith("payment:"):
            order_id = int(return_to.split(":")[-1])
            await _send_invoice_message(message, order_id, language)

    @router.callback_query(F.data.startswith("order:pay:"))
    async def order_payment_method_handler(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, order_id, _ = callback.data.split(":")
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            if order is None:
                await callback.answer()
                return
        await state.clear()
        await callback.answer()
        await _show_invoice(callback, order, language)

    @router.callback_query(F.data.startswith("order:cancel:"))
    async def order_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        order_id = int(callback.data.split(":")[-1])
        order_number = "-"
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, order_id)
            if order is not None:
                order_number = order.order_number
                if order.user and order.user.telegram_id == callback.from_user.id and order.status != OrderStatus.COMPLETED:
                    await change_status(session, order, OrderStatus.CANCELLED, changed_by_telegram_id=callback.from_user.id)
                    await session.commit()
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "order_cancelled", order_number=order_number),
            reply_markup=build_menu_only_markup(language),
        )

    @router.message(UserFlowState.waiting_payment_proof, F.photo)
    async def payment_photo_handler(message: Message, state: FSMContext) -> None:
        await _redirect_to_checkout(message, state)

    @router.message(UserFlowState.waiting_payment_proof, F.document)
    async def payment_document_handler(message: Message, state: FSMContext) -> None:
        await _redirect_to_checkout(message, state)

    @router.message(UserFlowState.waiting_payment_proof)
    async def payment_invalid_handler(message: Message, state: FSMContext) -> None:
        await _redirect_to_checkout(message, state)

    return router
