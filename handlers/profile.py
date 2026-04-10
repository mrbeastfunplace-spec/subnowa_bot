from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from handlers.common import completed_orders_markup, order_detail_markup
from services.context import AppContext
from services.texts import format_text
from services.users import get_user_by_telegram_id, get_user_language, list_completed_orders_for_user
from utils.formatting import format_money, order_display_number, order_status_label, user_display_name
from utils.messages import answer_or_edit


def build_profile_router(app: AppContext) -> Router:
    router = Router(name="profile")

    @router.callback_query(F.data == "menu:profile")
    async def profile_handler(callback: CallbackQuery) -> None:
        async with app.session_factory() as session:
            language = await get_user_language(session, callback.from_user.id, app.settings.default_language)
            title = await format_text(session, "user.profile_title", language, fallback="Профиль")
        display_name = escape(user_display_name(callback.from_user, callback.from_user.id))
        history_text = "📜 История заказов" if language == "ru" else ("📜 Buyurtmalar tarixi" if language == "uz" else "📜 Order history")
        menu_text = "🏠 Меню" if language == "ru" else ("🏠 Menyu" if language == "uz" else "🏠 Menu")
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{title}</b>\n\nПользователь: <b>{display_name}</b>\nID: <code>{callback.from_user.id}</code>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=history_text, callback_data="profile:history")],
                    [InlineKeyboardButton(text=menu_text, callback_data="menu:main")],
                ]
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
                    inline_keyboard=[[InlineKeyboardButton(text="◀ Назад", callback_data="menu:profile")]]
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
            orders = await list_completed_orders_for_user(session, user.id) if user else []
            order = next((item for item in orders if item.id == order_id), None)
        await callback.answer()
        if order is None:
            await answer_or_edit(callback, "Заказ не найден.")
            return
        order_no_label = "Номер" if language == "ru" else ("Raqam" if language == "uz" else "Number")
        status_label = "Статус" if language == "ru" else ("Holat" if language == "uz" else "Status")
        amount_label = "Сумма" if language == "ru" else ("Summa" if language == "uz" else "Amount")
        text = (
            f"<b>{order.product_name_snapshot}</b>\n\n"
            f"{order_no_label}: <code>{order_display_number(order)}</code>\n"
            f"{status_label}: {order_status_label(order.status.value, language)}\n"
            f"{amount_label}: {format_money(order.amount, order.currency)}"
        )
        await answer_or_edit(callback, text, reply_markup=order_detail_markup(order, language))

    return router
