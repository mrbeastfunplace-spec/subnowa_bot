from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from handlers.common import completed_orders_markup, order_detail_markup, profile_markup
from services.context import AppContext
from services.orders import get_order_by_id
from services.texts import format_text
from services.users import get_user_by_telegram_id, get_user_language, list_completed_orders_for_user
from states import UserFlowState
from utils.formatting import (
    format_datetime_local,
    format_money,
    order_display_number,
    order_duration_label,
    order_status_label,
    resolve_order_expiration,
    user_display_name,
)
from utils.messages import answer_or_edit


def build_profile_router(app: AppContext) -> Router:
    router = Router(name="profile_v2")

    def _detail_labels(language: str) -> dict[str, str]:
        if language == "uz":
            return {
                "order_no": "Buyurtma",
                "status": "Holat",
                "amount": "Summa",
                "created": "Rasmiylashtirilgan sana",
                "duration": "Amal qilish muddati",
                "expires": "Tugash sanasi",
                "payment": "To'lov usuli",
                "gmail": "Gmail",
                "login": "Login",
                "password": "Parol",
            }
        if language == "en":
            return {
                "order_no": "Order",
                "status": "Status",
                "amount": "Amount",
                "created": "Created at",
                "duration": "Duration",
                "expires": "End date",
                "payment": "Payment",
                "gmail": "Gmail",
                "login": "Login",
                "password": "Password",
            }
        return {
            "order_no": "Номер заказа",
            "status": "Статус",
            "amount": "Сумма",
            "created": "Дата оформления",
            "duration": "Срок действия",
            "expires": "Дата окончания",
            "payment": "Оплата",
            "gmail": "Gmail",
            "login": "Логин",
            "password": "Пароль",
        }

    @router.callback_query(F.data == "menu:profile")
    async def profile_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            title = await format_text(session, "user.profile_title", language, fallback="Профиль")
        display_name = escape(user_display_name(callback.from_user, callback.from_user.id))
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{title}</b>\n\nПользователь: <b>{display_name}</b>\nID: <code>{callback.from_user.id}</code>",
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

    @router.callback_query(F.data == "profile:history")
    async def profile_history_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            orders = await list_completed_orders_for_user(session, user.id) if user else []
            title = await format_text(session, "user.order_history_title", language, fallback="История заказов")
            empty_text = await format_text(session, "user.no_completed_orders", language, fallback="Нет завершённых заказов.")
        await callback.answer()
        if not orders:
            await answer_or_edit(
                callback,
                empty_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile", style="danger")]]
                ),
            )
            return
        await answer_or_edit(callback, f"<b>{title}</b>", reply_markup=completed_orders_markup(orders, language))

    @router.callback_query(F.data.startswith("order:detail:"))
    async def order_detail_handler(callback: CallbackQuery) -> None:
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            user = await get_user_by_telegram_id(session, callback.from_user.id)
            order = await get_order_by_id(session, order_id) if user else None
        await callback.answer()
        if order is None or user is None or order.user_id != user.id:
            await answer_or_edit(callback, "Заказ не найден.")
            return
        labels = _detail_labels(language)
        details = order.details or {}
        lines = [
            f"<b>{escape(order.product_name_snapshot)}</b>",
            "",
            f"{labels['order_no']}: <code>{order_display_number(order)}</code>",
            f"{labels['status']}: {order_status_label(order.status.value, language)}",
            f"{labels['amount']}: {format_money(order.amount, order.currency)}",
            f"{labels['created']}: {format_datetime_local(order.created_at)}",
            f"{labels['duration']}: {order_duration_label(order.product_code_snapshot, language)}",
            f"{labels['expires']}: {format_datetime_local(resolve_order_expiration(order))}",
        ]
        if order.payment_method is not None:
            lines.append(f"{labels['payment']}: {escape(order.payment_method.admin_title)}")
        gmail = details.get("gmail")
        if gmail:
            lines.append(f"{labels['gmail']}: <code>{escape(str(gmail))}</code>")
        capcut_login = details.get("capcut_login")
        capcut_password = details.get("capcut_password")
        if capcut_login:
            lines.append(f"{labels['login']}: <code>{escape(str(capcut_login))}</code>")
        if capcut_password:
            lines.append(f"{labels['password']}: <code>{escape(str(capcut_password))}</code>")
        await answer_or_edit(
            callback,
            "\n".join(lines),
            reply_markup=order_detail_markup(order, language, app.settings.support_url),
        )

    return router
