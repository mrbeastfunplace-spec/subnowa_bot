from __future__ import annotations

from decimal import Decimal
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handlers.common import (
    order_detail_markup,
    profile_markup,
    topup_amounts_markup,
    topup_methods_markup,
    topup_receipt_markup,
)
from services.balance import list_balance_transactions
from services.context import AppContext
from services.orders import get_order_by_id, list_orders_for_user
from services.payments import get_payment_method_by_code, payment_instruction, payment_title
from services.texts import format_text
from services.topups import create_topup
from services.users import count_orders_for_user, get_user_by_telegram_id, get_user_language
from states import UserFlowState
from utils.formatting import (
    format_datetime_local,
    format_money,
    order_display_number,
    order_status_label,
)
from utils.messages import answer_or_edit


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _balance_tx_label(tx_type: str) -> str:
    mapping = {
        "topup": "✅ Пополнение",
        "purchase": "🛒 Покупка",
        "refund": "↩️ Возврат",
        "admin_adjustment": "🛠 Корректировка",
    }
    return mapping.get(tx_type, tx_type)


def _profile_text(user, orders_count: int) -> str:
    username = f"@{user.username.lstrip('@')}" if (user.username or "").strip() else "—"
    return (
        "<b>👤 Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"👤 Username: {escape(username)}\n"
        f"💰 Баланс: {format_money(user.balance, 'сум').replace(' сум', '')} сум\n"
        f"🛒 Покупок: {orders_count}\n"
        f"📅 Регистрация: {format_datetime_local(user.created_at)}"
    )


def _orders_markup(orders: list, language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{order_display_number(order)} • {order.product_name_snapshot}", callback_data=f"order:detail:{order.id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _notify_admins_about_topup(
    bot: Bot,
    app: AppContext,
    *,
    topup,
    user,
    payment_title_text: str,
    receipt_file_id: str,
    receipt_file_type: str,
) -> None:
    caption = (
        "🆕 Новая заявка на пополнение\n\n"
        f"👤 Пользователь: @{user.username or 'нет'}\n"
        f"🆔 ID: <code>{user.telegram_id}</code>\n"
        f"💰 Сумма: {format_money(topup.amount, 'сум').replace(' сум', '')} сум\n"
        f"💳 Способ: {escape(payment_title_text)}\n"
        "⏳ Статус: Ожидает проверки\n\n"
        "Проверьте оплату и выберите действие."
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:topup:approve:{topup.id}")],
            [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:topup:reject:{topup.id}", style="danger")],
            [InlineKeyboardButton(text="👤 Профиль клиента", callback_data=f"admin:user:view:{user.id}")],
        ]
    )
    for admin_id in app.settings.admin_ids:
        try:
            if receipt_file_type == "photo":
                await bot.send_photo(admin_id, photo=receipt_file_id, caption=caption, reply_markup=markup)
            else:
                await bot.send_document(admin_id, document=receipt_file_id, caption=caption, reply_markup=markup)
        except Exception:
            continue


def build_profile_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="profile")

    @router.callback_query(F.data == "menu:profile")
    async def profile_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            orders_count = await count_orders_for_user(session, user.id)
        await callback.answer()
        await answer_or_edit(
            callback,
            _profile_text(user, orders_count),
            reply_markup=profile_markup(language, app.settings.support_url),
        )

    @router.callback_query(F.data == "profile:promo")
    async def profile_promo_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            prompt = await format_text(session, "user.promo_enter", language, fallback="Введите промокод.")
        await state.set_state(UserFlowState.waiting_promo_code)
        await state.update_data(promo_return="profile")
        await callback.answer()
        await answer_or_edit(
            callback,
            prompt,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "profile:topup")
    async def profile_topup_handler(callback: CallbackQuery, state: FSMContext) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            "<b>💳 Пополнение баланса</b>\n\nВыберите сумму пополнения:",
            reply_markup=topup_amounts_markup(language),
        )

    @router.callback_query(F.data.startswith("topup:amount:"))
    async def topup_amount_handler(callback: CallbackQuery, state: FSMContext) -> None:
        amount_token = callback.data.split(":")[-1]
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        if amount_token == "custom":
            await state.set_state(UserFlowState.waiting_topup_custom_amount)
            await callback.answer()
            await answer_or_edit(
                callback,
                "Введите сумму пополнения в сумах:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="profile:topup", style="danger")]]
                ),
            )
            return
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{int(amount_token):,} сум".replace(",", " "),
            reply_markup=topup_methods_markup(language, amount_token),
        )

    @router.message(UserFlowState.waiting_topup_custom_amount)
    async def topup_custom_amount_handler(message: Message, state: FSMContext) -> None:
        raw_value = (message.text or "").replace(" ", "").strip()
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await message.answer("Введите сумму целым числом в сумах.")
            return
        async with app.session_factory() as session:
            language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        await state.clear()
        await message.answer(
            f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{int(raw_value):,} сум".replace(",", " "),
            reply_markup=topup_methods_markup(language, raw_value),
        )

    @router.callback_query(F.data.startswith("topup:method:"))
    async def topup_method_handler(callback: CallbackQuery, state: FSMContext) -> None:
        _, _, amount_value, method_code = callback.data.split(":")
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            payment_method = await get_payment_method_by_code(session, method_code)
            if payment_method is None:
                await callback.answer("Способ оплаты не найден.", show_alert=True)
                return
            instruction = payment_instruction(payment_method, language)
            payment_name = payment_title(payment_method, language)
        await state.set_state(UserFlowState.waiting_topup_receipt)
        await state.update_data(topup_amount=amount_value, topup_method=method_code)
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>💳 Оплата через {escape(payment_name)}</b>\n\n"
            f"Сумма: {int(amount_value):,} сум\n\n".replace(",", " ")
            + instruction
            + "\n\nПосле оплаты отправьте чек или скриншот сюда.",
            reply_markup=topup_receipt_markup(language, amount_value),
        )

    @router.callback_query(F.data.startswith("topup:back:"))
    async def topup_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
        amount_value = callback.data.split(":")[-1]
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
        await state.clear()
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>💳 Выберите способ оплаты</b>\n\nСумма пополнения:\n{int(amount_value):,} сум".replace(",", " "),
            reply_markup=topup_methods_markup(language, amount_value),
        )

    @router.message(UserFlowState.waiting_topup_receipt, F.photo)
    async def topup_receipt_photo_handler(message: Message, state: FSMContext) -> None:
        await _handle_topup_receipt(message, state, app, bot, file_id=message.photo[-1].file_id, file_type="photo")

    @router.message(UserFlowState.waiting_topup_receipt, F.document)
    async def topup_receipt_document_handler(message: Message, state: FSMContext) -> None:
        await _handle_topup_receipt(message, state, app, bot, file_id=message.document.file_id, file_type="document")

    @router.message(UserFlowState.waiting_topup_receipt)
    async def topup_receipt_invalid_handler(message: Message) -> None:
        await message.answer("Отправьте чек фотографией или документом.")

    @router.callback_query(F.data == "profile:history")
    async def profile_history_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            history = await list_balance_transactions(session, user.id, limit=10)
        lines = ["<b>📜 История баланса</b>", ""]
        if not history:
            lines.append("Операций пока нет.")
        else:
            for index, item in enumerate(history, start=1):
                amount_text = format_money(abs(item.amount), "сум").replace(" сум", "")
                sign = "+" if Decimal(str(item.amount)) >= 0 else "-"
                lines.append(f"{index}. {_balance_tx_label(item.type.value)}: {sign}{amount_text} сум")
        lines.append("")
        lines.append(f"Текущий баланс: {format_money(user.balance, 'сум').replace(' сум', '')} сум")
        await callback.answer()
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
            ),
        )

    @router.callback_query(F.data == "profile:orders")
    async def profile_orders_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            orders = await list_orders_for_user(session, user.id, limit=20)
        if not orders:
            await callback.answer()
            await answer_or_edit(
                callback,
                "<b>📦 Ваши заказы</b>\n\nЗаказов пока нет.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
                ),
            )
            return
        await callback.answer()
        await answer_or_edit(callback, "<b>📦 Ваши заказы</b>", reply_markup=_orders_markup(orders, "ru"))

    @router.callback_query(F.data.startswith("order:detail:"))
    async def order_detail_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            if user is None:
                await callback.answer()
                return
            order = await get_order_by_id(session, order_id)
        await callback.answer()
        if order is None or order.user_id != user.id:
            await answer_or_edit(callback, "Заказ не найден.")
            return
        lines = [
            f"<b>{order_display_number(order)}</b>",
            f"💎 {escape(order.service_name_snapshot or order.product_name_snapshot)}",
            f"📦 {escape(order.product_type_snapshot or '-')}",
            f"💰 {format_money(order.amount, order.currency)}",
            f"⏳ {order_status_label(order.status.value, language)}",
        ]
        if (order.delivery_content or "").strip():
            lines.extend(["", "Данные по заказу:", escape(order.delivery_content)])
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=order_detail_markup(order, language, app.settings.support_url),
        )

    return router


async def _handle_topup_receipt(
    message: Message,
    state: FSMContext,
    app: AppContext,
    bot: Bot,
    *,
    file_id: str,
    file_type: str,
) -> None:
    data = await state.get_data()
    amount_value = data.get("topup_amount")
    method_code = data.get("topup_method")
    if not amount_value or not method_code:
        await message.answer("Данные пополнения не найдены. Начните заново из профиля.")
        await state.clear()
        return

    async with app.session_factory() as session:
        user = await get_user_by_telegram_id(session, message.from_user.id)
        language = await get_user_language(session, message.from_user.id, app.settings.default_language)
        payment_method = await get_payment_method_by_code(session, method_code)
        if user is None or payment_method is None:
            await message.answer("Не удалось создать заявку на пополнение.")
            await state.clear()
            return
        topup = await create_topup(
            session,
            user=user,
            amount=amount_value,
            payment_method=payment_method.code,
            receipt_file_id=file_id,
            receipt_file_type=file_type,
        )
        await session.commit()
        payment_name = payment_title(payment_method, language)

    await state.clear()
    await message.answer(
        "✅ Заявка на пополнение создана\n\n"
        f"💰 Сумма: {int(amount_value):,} сум\n".replace(",", " ")
        + f"💳 Способ: {payment_name}\n"
        + "⏳ Статус: Ожидает проверки\n\n"
        + "Администратор проверит оплату и зачислит баланс.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]]
        ),
    )
    await _notify_admins_about_topup(
        bot,
        app,
        topup=topup,
        user=user,
        payment_title_text=payment_name,
        receipt_file_id=file_id,
        receipt_file_type=file_type,
    )
