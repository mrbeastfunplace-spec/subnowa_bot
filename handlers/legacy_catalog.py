from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.base import CheckoutSessionStatus, OrderStatus
from handlers.common import insufficient_balance_markup, profile_markup, purchase_confirmation_markup
from services.catalog import get_product, get_product_by_code, product_type_label, service_name
from services.checkout import cancel_checkout_session, claim_checkout_processing, create_checkout_session, get_checkout_session
from services.context import AppContext
from services.inventory import count_available_inventory
from services.legacy_ui import (
    build_capcut_details_markup,
    build_capcut_selector_markup,
    build_chatgpt_menu_markup,
    build_gmail_choice_markup,
    build_invoice_markup,
    build_menu_only_markup,
    build_other_menu_markup,
    build_payment_back_markup,
    build_single_back_markup,
    build_stock_empty_markup,
    build_subscription_check_markup,
    build_subscriptions_markup,
    capcut_personal_text,
    capcut_ready_text,
    crypto_price_for_product,
    invoice_text,
    multi_service_name,
    other_request_name,
    payment_instruction_text,
    text as ui_text,
)
from services.orders import attach_payment_method, change_status, create_custom_request, create_order, get_order_by_id, save_payment_proof
from services.payments import get_payment_method, list_product_payment_methods
from services.purchases import execute_checkout
from services.settings import get_setting
from services.users import get_last_chatgpt_gmail, get_user_by_telegram_id, get_user_language, touch_user, user_has_trial
from states import UserFlowState
from utils.formatting import format_money, user_display_name
from utils.messages import answer_or_edit


GMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", re.IGNORECASE)
CARD_NUMBER = "9860100126034816"
USDT_TRC20_ADDRESS = "TUr3m7sAWpiysQs5S1jQkbxcvJARqAD8Rs"
CLICK_QR_IMAGE_PATH = Path(__file__).resolve().parents[1] / "media" / "click.png.jpg"


def _is_valid_gmail(value: str) -> bool:
    return bool(GMAIL_PATTERN.match(value.strip()))


def _is_valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.match(value.strip()))


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


def _sum_text(value: Decimal | int | float | str) -> str:
    return format_money(value, "сум").replace(" сум", "") + " сум"


def _chatgpt_variant_markup(language: str, personal_product, ready_product) -> InlineKeyboardMarkup:
    ready_callback = f"buy_balance:{ready_product.id}" if ready_product is not None else "chatgpt_1m"
    personal_price = _sum_text(personal_product.price if personal_product is not None else 79000)
    ready_price = _sum_text(ready_product.price if ready_product is not None else 49000)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Личный аккаунт — 79 000 сум", callback_data="buy_chatgpt_1m", style="success")],
            [InlineKeyboardButton(text="📦 Готовый аккаунт — 49 000 сум", callback_data=ready_callback, style="success")],
            [
                InlineKeyboardButton(text=ui_text(language, "btn_back"), callback_data="open_chatgpt", style="danger"),
                InlineKeyboardButton(text=ui_text(language, "btn_menu"), callback_data="menu:main"),
            ],
        ]
    )


def _insufficient_balance_text(product, balance_amount, language: str) -> str:
    missing = max(Decimal(str(product.price)) - Decimal(str(balance_amount)), Decimal("0.00"))
    return (
        "❌ Недостаточно средств\n\n"
        f"💎 Товар: {escape(service_name(product, language))}\n"
        f"📦 Вариант: {escape(product_type_label(product, language))}\n"
        f"💰 Цена: {_sum_text(product.price)}\n"
        f"💳 Ваш баланс: {_sum_text(balance_amount)}\n"
        f"➖ Не хватает: {_sum_text(missing)}\n\n"
        "Пополните баланс, чтобы продолжить оформление заказа."
    )


def _checkout_confirmation_text(product, balance_amount, language: str) -> str:
    balance_after = Decimal(str(balance_amount)) - Decimal(str(product.price))
    return (
        "✅ Подтверждение покупки\n\n"
        f"💎 Товар: {escape(service_name(product, language))}\n"
        f"📦 Вариант: {escape(product_type_label(product, language))}\n"
        f"💰 Цена: {_sum_text(product.price)}\n"
        f"💳 Ваш баланс: {_sum_text(balance_amount)}\n\n"
        f"После подтверждения с вашего баланса будет списано:\n➖ {_sum_text(product.price)}\n\n"
        "Остаток после оплаты:\n"
        f"💰 {_sum_text(balance_after)}\n\n"
        "Подтверждаете покупку?"
    )


def _processing_paid_text(order, balance_after) -> str:
    return (
        "✅ Оплата прошла успешно\n\n"
        f"💎 Сервис: {escape(order.service_name_snapshot or order.product_name_snapshot)}\n"
        f"📦 Вариант: {escape(order.product_type_snapshot or '-')}\n"
        f"💰 Списано: {_sum_text(order.amount)}\n"
        f"💳 Остаток: {_sum_text(balance_after)}\n\n"
        "Ваш заказ принят в обработку.\nОжидайте подтверждения администратора."
    )


def _ready_paid_text(order, balance_after, delivery_content: str) -> str:
    return (
        "✅ Ваш заказ подтверждён\n\n"
        f"💎 Сервис: {escape(order.service_name_snapshot or order.product_name_snapshot)}\n"
        f"📦 Тип: {escape(order.product_type_snapshot or '-')}\n"
        f"💰 Списано: {_sum_text(order.amount)}\n"
        f"💳 Остаток: {_sum_text(balance_after)}\n\n"
        "Данные по заказу:\n"
        f"{escape(delivery_content)}\n\n"
        "Спасибо за покупку!"
    )


async def _notify_admin_paid_balance_order(bot: Bot, app: AppContext, order, user) -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнить заказ", callback_data=f"admin:order:deliver:{order.id}")],
            [InlineKeyboardButton(text="❌ Отменить с возвратом", callback_data=f"admin:order:refund:{order.id}", style="danger")],
            [InlineKeyboardButton(text="👤 Профиль клиента", callback_data=f"admin:user:view:{user.id}")],
        ]
    )
    text_value = (
        "🆕 Новый оплаченный заказ\n\n"
        f"👤 Клиент: @{user.username or 'нет'}\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"💎 Сервис: {escape(order.service_name_snapshot or order.product_name_snapshot)}\n"
        f"📦 Вариант: {escape(order.product_type_snapshot or '-')}\n"
        f"💰 Оплачено: {_sum_text(order.amount)}\n\n"
        "Выполните заказ и отправьте данные клиенту."
    )
    for admin_id in app.settings.admin_ids:
        try:
            await bot.send_message(admin_id, text_value, reply_markup=markup)
        except Exception:
            continue


async def _start_balance_checkout(
    callback: CallbackQuery,
    state: FSMContext,
    app: AppContext,
    *,
    product,
    language: str,
    payload: dict | None = None,
    back_callback: str,
    alternate_callback: str | None = None,
) -> None:
    async with app.session_factory() as session:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        if user is None:
            await callback.answer()
            return
        if (product.product_type or "") == "ready_access":
            available = await count_available_inventory(session, product.id)
            if available <= 0:
                await callback.answer()
                await answer_or_edit(
                    callback,
                    "❌ Сейчас нет доступных готовых вариантов\n\nВы можете выбрать другой вариант или обратиться в поддержку.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="👤 Личный вариант", callback_data=alternate_callback or back_callback)],
                            [InlineKeyboardButton(text="💬 Поддержка", url=app.settings.support_url)],
                            [InlineKeyboardButton(text=ui_text(language, "btn_back"), callback_data=back_callback, style="danger")],
                            [InlineKeyboardButton(text=ui_text(language, "btn_menu"), callback_data="menu:main")],
                        ]
                    ),
                )
                return
        if Decimal(str(user.balance)) < Decimal(str(product.price)):
            await callback.answer()
            await answer_or_edit(
                callback,
                _insufficient_balance_text(product, user.balance, language),
                reply_markup=insufficient_balance_markup(language, back_callback),
            )
            return
        checkout = await create_checkout_session(
            session,
            user=user,
            product=product,
            payload={
                **(payload or {}),
                "back_callback": back_callback,
                "alternate_callback": alternate_callback or "",
            },
        )
        await session.commit()
    await state.clear()
    await callback.answer()
    await answer_or_edit(
        callback,
        _checkout_confirmation_text(product, user.balance, language),
        reply_markup=purchase_confirmation_markup(checkout.id, language),
    )


def build_catalog_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="legacy_catalog")

    async def _show_subscriptions(target: CallbackQuery, language: str) -> None:
        await answer_or_edit(
            target,
            f"<b>{ui_text(language, 'subscriptions_title')}</b>",
            reply_markup=build_subscriptions_markup(language),
        )

    async def _show_invoice(callback: CallbackQuery, order, language: str, payment_methods: list[object]) -> None:
        await answer_or_edit(
            callback,
            invoice_text(language, order.product_code_snapshot, order.order_number, order.amount),
            reply_markup=build_invoice_markup(language, order.id, payment_methods),
        )

    @router.callback_query(F.data.in_({"menu:catalog", "open_subscriptions"}))
    async def open_catalog_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            await touch_user(session, callback.from_user.id)
            await session.commit()
        await state.clear()
        await callback.answer()
        await _show_subscriptions(callback, language)

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
            reply_markup=build_chatgpt_menu_markup(language, app.settings.support_url, product.price if product else 79000),
        )

    @router.callback_query(F.data == "open_capcut")
    async def open_capcut_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            ui_text(language, "capcut_menu_text"),
            reply_markup=build_capcut_selector_markup(language),
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
            ready_product = await get_product_by_code(session, "chatgpt_ready_month")
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            "<tg-emoji emoji-id='5359726582447487916'>🤖</tg-emoji> ChatGPT Pro\n\nВыберите вариант подключения:",
            reply_markup=_chatgpt_variant_markup(language, ready_product),
        )

    @router.callback_query(F.data == "capcut_1m")
    async def capcut_1m_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await open_capcut_handler(callback, state)

    @router.callback_query(F.data == "capcut_personal")
    async def capcut_personal_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "capcut_personal_month")
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            capcut_personal_text(language, product.price if product else 79000),
            reply_markup=build_capcut_details_markup(language, "capcut_personal"),
        )

    @router.callback_query(F.data == "capcut_ready")
    async def capcut_ready_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "capcut_pro_month")
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            capcut_ready_text(language, product.price if product else 49000),
            reply_markup=build_capcut_details_markup(language, "capcut_ready"),
        )

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
        if not quantity_value.isdigit() or int(quantity_value) <= 0:
            await message.answer("Введите количество целым числом больше нуля.")
            return
        quantity = int(quantity_value)
        data = await state.get_data()
        service_label = data.get("service_name") or "Unknown"
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, message.from_user.id)
            if user is None:
                await message.answer("Пользователь не найден.")
                return
            order = await create_custom_request(session, user=user, language=language, note=f"{service_label} x {quantity}")
            order.product_name_snapshot = f"{service_label} x {quantity}"
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
            f"Сервис: {escape(service_label)}\n"
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
            if not _is_valid_email(gmail):
                await message.answer("Введите корректный email.")
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
            order.product_name_snapshot = "ChatGPT Trial 3 дня"
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
            product = await get_product_by_code(session, "chatgpt_plus_month")
            if product is None or not gmail:
                await callback.answer()
                return
        await _start_balance_checkout(
            callback,
            state,
            app,
            product=product,
            language=language,
            payload={"gmail": gmail},
            back_callback="chatgpt_1m",
        )

    @router.callback_query(F.data == "buy_capcut_1m")
    async def buy_capcut_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await buy_capcut_ready_handler(callback, state)

    @router.callback_query(F.data == "buy_capcut_ready")
    async def buy_capcut_ready_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "capcut_pro_month")
            if product is None:
                await callback.answer()
                return
        await _start_balance_checkout(
            callback,
            state,
            app,
            product=product,
            language=language,
            back_callback="capcut_ready",
            alternate_callback="capcut_personal",
        )

    @router.callback_query(F.data == "buy_capcut_personal")
    async def buy_capcut_personal_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product_by_code(session, "capcut_personal_month")
            if product is None:
                await callback.answer()
                return
        await _start_balance_checkout(
            callback,
            state,
            app,
            product=product,
            language=language,
            back_callback="capcut_personal",
            alternate_callback="capcut_ready",
        )

    @router.callback_query(F.data.startswith("buy_balance:"))
    async def buy_balance_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product(session, product_id)
            if product is None:
                await callback.answer()
                return
            back_callback = "chatgpt_1m" if (product.service_name or "").startswith("ChatGPT") else "open_subscriptions"
            alternate_callback = "buy_chatgpt_1m" if (product.service_name or "").startswith("ChatGPT") else None
        await _start_balance_checkout(
            callback,
            state,
            app,
            product=product,
            language=language,
            back_callback=back_callback,
            alternate_callback=alternate_callback,
        )

    @router.callback_query(F.data.startswith("checkout:pay:"))
    async def checkout_pay_handler(callback: CallbackQuery) -> None:
        checkout_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            checkout = await get_checkout_session(session, checkout_id)
            if checkout is None:
                await callback.answer()
                await answer_or_edit(callback, "⚠️ Этот заказ уже обработан\n\nПроверьте раздел “Мои заказы”.")
                return
            if checkout.status == CheckoutSessionStatus.COMPLETED:
                await callback.answer()
                await answer_or_edit(callback, "⚠️ Этот заказ уже обработан\n\nПроверьте раздел “Мои заказы”.")
                return
            if not await claim_checkout_processing(session, checkout_id):
                await session.commit()
                await callback.answer()
                await answer_or_edit(callback, "⚠️ Этот заказ уже обработан\n\nПроверьте раздел “Мои заказы”.")
                return
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            result = await execute_checkout(session, checkout_id=checkout_id, language=language)
            await session.commit()

        if not result.ok:
            await callback.answer()
            if result.reason == "stock_empty":
                await answer_or_edit(
                    callback,
                    "❌ Сейчас нет доступных готовых вариантов\n\nВы можете выбрать другой вариант или обратиться в поддержку.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="profile:topup")],
                            [InlineKeyboardButton(text=ui_text(language, "btn_menu"), callback_data="menu:main")],
                        ]
                    ),
                )
                return
            if result.reason == "insufficient_balance" and result.product is not None and result.user is not None:
                back_callback = (result.checkout.payload or {}).get("back_callback") or "open_subscriptions"
                await answer_or_edit(
                    callback,
                    _insufficient_balance_text(result.product, result.user.balance, language),
                    reply_markup=insufficient_balance_markup(language, back_callback),
                )
                return
            await answer_or_edit(callback, "⚠️ Этот заказ уже обработан\n\nПроверьте раздел “Мои заказы”.")
            return

        await callback.answer()
        if result.reason == "completed":
            await answer_or_edit(
                callback,
                _ready_paid_text(result.order, result.user.balance, result.delivery_content or ""),
                reply_markup=build_menu_only_markup(language),
            )
            return

        await answer_or_edit(
            callback,
            _processing_paid_text(result.order, result.user.balance),
            reply_markup=build_menu_only_markup(language),
        )
        await _notify_admin_paid_balance_order(bot, app, result.order, result.user)

    @router.callback_query(F.data.startswith("checkout:cancel:"))
    async def checkout_cancel_handler(callback: CallbackQuery) -> None:
        checkout_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            checkout = await get_checkout_session(session, checkout_id)
            if checkout is not None and checkout.status == CheckoutSessionStatus.PENDING:
                await cancel_checkout_session(session, checkout)
                await session.commit()
        await callback.answer()
        await answer_or_edit(
            callback,
            "❌ Покупка отменена\n\nДеньги с баланса не списаны.",
            reply_markup=build_menu_only_markup("ru"),
        )

    @router.callback_query(F.data.startswith("product:view:"))
    async def legacy_product_view_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
        if product is None:
            await callback.answer()
            return
        if product.code in {"chatgpt_plus_month", "chatgpt_ready_month"}:
            await chatgpt_1m_handler(callback, state)
            return
        if product.code == "capcut_pro_month":
            await open_capcut_handler(callback, state)
            return
        if product.code == "capcut_personal_month":
            await capcut_personal_handler(callback, state)
            return
        await open_catalog_handler(callback, state)

    @router.callback_query(F.data == "product:trial")
    async def legacy_trial_alias_handler(callback: CallbackQuery, state: FSMContext) -> None:
        await chatgpt_trial_handler(callback, state)

    @router.callback_query(F.data.startswith("product:buy:"))
    async def legacy_product_buy_handler(callback: CallbackQuery, state: FSMContext) -> None:
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            product = await get_product(session, product_id)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if product is None:
                await callback.answer()
                return
            if product.code == "chatgpt_plus_month":
                await buy_chatgpt_handler(callback, state)
                return
            if product.code == "chatgpt_ready_month":
                await _start_balance_checkout(
                    callback,
                    state,
                    app,
                    product=product,
                    language=language,
                    back_callback="chatgpt_1m",
                    alternate_callback="buy_chatgpt_1m",
                )
                return
            if product.code == "capcut_pro_month":
                await buy_capcut_ready_handler(callback, state)
                return
            if product.code == "capcut_personal_month":
                await buy_capcut_personal_handler(callback, state)
                return
            if user is None:
                await callback.answer()
                return
            order = await create_order(session, user=user, product=product, language=language)
            payment_methods = await list_product_payment_methods(session, product)
            await session.commit()
        await state.clear()
        await callback.answer()
        await _show_invoice(callback, order, language, payment_methods)

    @router.callback_query(F.data.startswith("order:payment_methods:"))
    async def order_payment_methods_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, order_id)
            if order is None or order.product is None:
                await callback.answer()
                return
            payment_methods = await list_product_payment_methods(session, order.product)
        await callback.answer()
        await _show_invoice(callback, order, language, payment_methods)

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
                    "<b>👤 Ваш профиль</b>\n\n"
                    f"Пользователь: <b>{display_name}</b>\nID: <code>{message.from_user.id}</code>",
                    reply_markup=profile_markup(language, app.settings.support_url),
                )
                return
            if isinstance(return_to, str) and return_to.startswith("payment:"):
                order_id = int(return_to.split(":")[-1])
                order = await get_order_by_id(session, order_id)
                if order is None or order.product is None:
                    return
                payment_methods = await list_product_payment_methods(session, order.product)
                await message.answer(
                    invoice_text(language, order.product_code_snapshot, order.order_number, order.amount),
                    reply_markup=build_invoice_markup(language, order.id, payment_methods),
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
            await session.commit()
        await state.set_state(UserFlowState.waiting_payment_proof)
        await state.update_data(order_id=int(order_id))
        payment_text = payment_instruction_text(
            language,
            payment_method.code,
            order.order_number,
            order.product_name_snapshot,
            order.amount,
            crypto_price_for_product(order.product_code_snapshot),
            CARD_NUMBER,
            USDT_TRC20_ADDRESS,
        )
        await callback.answer()
        if payment_method.code == "click" and CLICK_QR_IMAGE_PATH.exists():
            if callback.message is not None:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
            await bot.send_photo(
                callback.from_user.id,
                photo=FSInputFile(str(CLICK_QR_IMAGE_PATH)),
                caption=payment_text,
                reply_markup=build_payment_back_markup(language, int(order_id), app.settings.support_url),
            )
            return
        await answer_or_edit(
            callback,
            payment_text,
            reply_markup=build_payment_back_markup(language, int(order_id), app.settings.support_url),
        )

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
        data = await state.get_data()
        order_id = data.get("order_id")
        if not order_id:
            await message.answer("Заказ для чека не найден.")
            return
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            if order is None:
                await message.answer("Заказ не найден.")
                return
            await save_payment_proof(session, order, message.photo[-1].file_id, "photo", changed_by_telegram_id=message.from_user.id)
            await session.commit()
        await state.clear()
        await message.answer(ui_text(language, "payment_check_saved"))
        for admin_id in app.settings.admin_ids:
            try:
                await bot.send_photo(
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=(
                        "Новый чек\n\n"
                        f"Заказ: <code>{order.order_number}</code>\n"
                        f"Пользователь: <b>{escape(user_display_name(message.from_user, message.from_user.id))}</b>\n"
                        f"Товар: {escape(order.product_name_snapshot)}"
                    ),
                    reply_markup=_admin_order_markup(order.id),
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
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
            order = await get_order_by_id(session, int(order_id))
            if order is None:
                await message.answer("Заказ не найден.")
                return
            await save_payment_proof(session, order, message.document.file_id, "document", changed_by_telegram_id=message.from_user.id)
            await session.commit()
        await state.clear()
        await message.answer(ui_text(language, "payment_check_saved"))
        for admin_id in app.settings.admin_ids:
            try:
                await bot.send_document(
                    admin_id,
                    document=message.document.file_id,
                    caption=(
                        "Новый чек\n\n"
                        f"Заказ: <code>{order.order_number}</code>\n"
                        f"Пользователь: <b>{escape(user_display_name(message.from_user, message.from_user.id))}</b>\n"
                        f"Товар: {escape(order.product_name_snapshot)}"
                    ),
                    reply_markup=_admin_order_markup(order.id),
                )
            except Exception:
                continue

    @router.message(UserFlowState.waiting_payment_proof)
    async def payment_invalid_handler(message: Message) -> None:
        await message.answer("Отправьте чек фотографией или документом.")

    return router
