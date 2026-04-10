from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select

from db.base import ButtonActionType, Language, OrderStatus, PaymentProviderType, ProductStatus
from db.models import CapCutAccount, Category, Layout, LayoutButton, LayoutButtonTranslation, Order, PaymentMethod, PaymentMethodTranslation, Product, ProductPaymentMethod, ProductTranslation, TextEntry, TextTranslation
from services.admin import build_stats_text
from services.buttons import build_layout_markup, get_button, get_layout, list_layouts
from services.capcut import add_bulk_accounts, add_capcut_account, claim_free_account, count_free_accounts, list_accounts
from services.catalog import category_name, get_category, get_product, product_name
from services.context import AppContext
from services.orders import change_status, get_order_by_id, get_order_by_reference, list_orders
from services.payments import get_payment_method, payment_title, toggle_product_payment_method
from services.texts import format_text
from services.users import get_user_language
from states import AdminState
from utils.formatting import format_money, order_display_number, order_status_label, user_display_name
from utils.messages import answer_or_edit
from utils.translations import pick_translation


def build_admin_router(app: AppContext, bot: Bot) -> Router:
    router = Router(name="admin")

    def _guard(user_id: int) -> bool:
        return app.is_admin(user_id)

    def _back_main_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Назад в админку", callback_data="admin:main")]]
        )

    async def _render_admin_main(target: Message | CallbackQuery) -> None:
        async with app.session_factory() as session:
            markup = await build_layout_markup(session, "admin_main", "ru")
            title = await format_text(session, "admin.panel_title", "ru", fallback="Админ-панель")
        await answer_or_edit(target, f"<b>{title}</b>", reply_markup=markup)

    def _render_order_text(order: Order) -> str:
        details = order.details or {}
        display_name = escape(user_display_name(order.user))
        telegram_id = order.user.telegram_id if order.user else "-"
        return (
            f"<b>{escape(order.product_name_snapshot or 'Заказ')}</b>\n\n"
            f"Номер: <code>{order_display_number(order)}</code>\n"
            f"Код: <code>{order.order_number}</code>\n"
            f"Пользователь: <b>{display_name}</b>\n"
            f"Telegram ID: <code>{telegram_id}</code>\n"
            f"Статус: <b>{order_status_label(order.status.value, 'ru')}</b>\n"
            f"Сумма: <b>{format_money(order.amount, order.currency)}</b>\n"
            f"Метод оплаты: {escape(order.payment_method.admin_title) if order.payment_method else '-'}\n"
            f"Тип выдачи: {escape(order.delivery_type)}\n"
            f"Gmail: {escape(str(details.get('gmail', '-')))}\n"
            f"Комментарий: {escape(order.customer_note or '-')}"
        )

    def _order_actions_markup(order: Order) -> InlineKeyboardMarkup:
        rows: list[list[InlineKeyboardButton]] = []
        if order.status == OrderStatus.WAITING_CHECK:
            rows.append([InlineKeyboardButton(text="Подтвердить оплату", callback_data=f"admin:approve:{order.id}")])
            rows.append([InlineKeyboardButton(text="Отклонить", callback_data=f"admin:reject:{order.id}")])
        elif order.status in {OrderStatus.PAID, OrderStatus.PROCESSING}:
            rows.append([InlineKeyboardButton(text="Завершить", callback_data=f"admin:complete:{order.id}")])
            rows.append([InlineKeyboardButton(text="Отклонить", callback_data=f"admin:reject:{order.id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:orders")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _send_user_message(telegram_id: int, text: str) -> None:
        try:
            await bot.send_message(telegram_id, text)
        except Exception:
            pass

    def _product_list_markup(products: list[Product]) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=f"{product.code} ({product.status.value})", callback_data=f"admin:product:{product.id}")] for product in products]
        rows.append([InlineKeyboardButton(text="Добавить товар", callback_data="admin:products:add")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _payment_list_markup(items: list[PaymentMethod]) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=f"{item.admin_title} ({'on' if item.is_active else 'off'})", callback_data=f"admin:payment:{item.id}")] for item in items]
        rows.append([InlineKeyboardButton(text="Добавить метод", callback_data="admin:payments:add")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _stock_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Добавить аккаунт", callback_data="admin:stock:add")],
                [InlineKeyboardButton(text="Добавить пачкой", callback_data="admin:stock:bulk")],
                [InlineKeyboardButton(text="Свободные", callback_data="admin:stock:free")],
                [InlineKeyboardButton(text="Выданные", callback_data="admin:stock:used")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:main")],
            ]
        )

    def _text_pages_markup(entries: list[TextEntry], page: int, total_pages: int) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=entry.code, callback_data=f"admin:text:{entry.id}")] for entry in entries]
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀", callback_data=f"admin:texts:{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="▶", callback_data=f"admin:texts:{page + 1}"))
        if nav_row:
            rows.append(nav_row)
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _layouts_markup(layouts: list[Layout]) -> InlineKeyboardMarkup:
        rows = [[InlineKeyboardButton(text=f"{layout.scope}: {layout.title}", callback_data=f"admin:layout:{layout.id}")] for layout in layouts]
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    @router.message(Command("admin"))
    async def admin_command_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        await state.clear()
        await _render_admin_main(message)

    @router.message(Command("find_order"))
    async def admin_find_order_handler(message: Message) -> None:
        if not _guard(message.from_user.id):
            return
        reference = (message.text or "").partition(" ")[2].strip()
        if not reference:
            await message.answer("Используйте: <code>/find_order 123</code> или <code>/find_order #123</code>.")
            return
        async with app.session_factory() as session:
            order = await get_order_by_reference(session, reference)
        if order is None:
            await message.answer("Заказ не найден.")
            return
        await message.answer(_render_order_text(order), reply_markup=_order_actions_markup(order))

    @router.callback_query(F.data == "admin:main")
    async def admin_main_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.clear()
        await callback.answer()
        await _render_admin_main(callback)

    @router.callback_query(F.data == "admin:stats")
    async def admin_stats_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            text = await build_stats_text(session)
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_back_main_markup())

    @router.callback_query(F.data == "admin:orders")
    @router.callback_query(F.data.startswith("admin:orders:"))
    async def admin_orders_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        statuses = None
        title = "Последние заказы"
        if callback.data.count(":") == 2:
            status = callback.data.split(":")[-1]
            statuses = [status]
            title = f"Заказы: {order_status_label(status, 'ru')}"
        async with app.session_factory() as session:
            orders = await list_orders(session, statuses=statuses, limit=20)
        rows = [
            [InlineKeyboardButton(text=f"{order_display_number(order)} • {order.product_name_snapshot} • {order_status_label(order.status.value, 'ru')}", callback_data=f"admin:order:{order.id}")]
            for order in orders
        ]
        rows.append([
            InlineKeyboardButton(text="На проверке", callback_data="admin:orders:waiting_check"),
            InlineKeyboardButton(text="Оплачены", callback_data="admin:orders:paid"),
        ])
        rows.append([
            InlineKeyboardButton(text="В работе", callback_data="admin:orders:processing"),
            InlineKeyboardButton(text="Все", callback_data="admin:orders"),
        ])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:main")])
        await callback.answer()
        await answer_or_edit(
            callback,
            f"<b>{title}</b>\n\nПоиск: <code>/find_order 123</code> или <code>/find_order #123</code>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

    @router.callback_query(F.data.startswith("admin:order:"))
    async def admin_order_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
        await callback.answer()
        if order is None:
            await answer_or_edit(callback, "Заказ не найден.", reply_markup=_back_main_markup())
            return
        await answer_or_edit(callback, _render_order_text(order), reply_markup=_order_actions_markup(order))

    @router.callback_query(F.data.startswith("admin:approve:"))
    async def admin_approve_order_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            if order.workflow_type == "capcut_auto":
                account = await claim_free_account(session, order)
                if account is None:
                    await change_status(session, order, OrderStatus.PAID, callback.from_user.id, "payment approved, stock empty")
                    await session.commit()
                    await _send_user_message(order.user.telegram_id, "Оплата подтверждена, но склад CapCut сейчас пуст.")
                else:
                    await change_status(session, order, OrderStatus.COMPLETED, callback.from_user.id, "auto issued capcut account")
                    await session.commit()
                    await _send_user_message(
                        order.user.telegram_id,
                        "Оплата подтверждена.\n\n"
                        f"Ваш CapCut аккаунт:\nЛогин: <code>{account.login}</code>\nПароль: <code>{account.password}</code>",
                    )
            else:
                await change_status(session, order, OrderStatus.PAID, callback.from_user.id, "payment approved")
                await session.commit()
                await _send_user_message(order.user.telegram_id, "Оплата подтверждена. Заказ передан в работу.")
        await callback.answer("Готово")
        await admin_order_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:reject:"))
    async def admin_reject_order_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            await change_status(session, order, OrderStatus.REJECTED, callback.from_user.id, "rejected by admin")
            await session.commit()
            await _send_user_message(order.user.telegram_id, "Ваш заказ отклонён.")
        await callback.answer("Отклонено")
        await admin_order_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:complete:"))
    async def admin_complete_order_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        order_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            order = await get_order_by_id(session, order_id)
            if order is None:
                await callback.answer()
                return
            await change_status(session, order, OrderStatus.COMPLETED, callback.from_user.id, "completed by admin")
            await session.commit()
            await _send_user_message(order.user.telegram_id, "Ваш заказ завершён.")
        await callback.answer("Завершено")
        await admin_order_detail_handler(callback)

    @router.callback_query(F.data == "admin:stock")
    async def admin_stock_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            free_count = await count_free_accounts(session)
            used_count = await session.scalar(select(func.count(CapCutAccount.id)).where(CapCutAccount.is_used.is_(True))) or 0
        await callback.answer()
        await answer_or_edit(
            callback,
            "<b>Склад CapCut</b>\n\n"
            f"Свободных: <b>{free_count}</b>\n"
            f"Выданных: <b>{used_count}</b>",
            reply_markup=_stock_markup(),
        )

    @router.callback_query(F.data == "admin:stock:add")
    async def admin_stock_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_stock_single)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте аккаунт в формате <code>login|password</code>.", reply_markup=_back_main_markup())

    @router.callback_query(F.data == "admin:stock:bulk")
    async def admin_stock_bulk_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_stock_bulk)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте список аккаунтов, по одному на строку.\nФормат строки: <code>login|password</code>.", reply_markup=_back_main_markup())

    @router.callback_query(F.data == "admin:stock:free")
    @router.callback_query(F.data == "admin:stock:used")
    async def admin_stock_list_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        used = callback.data.endswith("used")
        async with app.session_factory() as session:
            accounts = await list_accounts(session, used=used, limit=30)
        lines = [f"<b>{'Выданные' if used else 'Свободные'} аккаунты</b>"]
        lines.append("")
        if not accounts:
            lines.append("Список пуст.")
        else:
            for account in accounts:
                suffix = f" -> order #{account.issued_order_id}" if account.issued_order_id else ""
                lines.append(f"<code>{account.login}</code> / <code>{account.password}</code>{suffix}")
        await callback.answer()
        await answer_or_edit(callback, "\n".join(lines), reply_markup=_stock_markup())

    @router.message(AdminState.waiting_stock_single)
    async def admin_stock_single_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        raw = (message.text or "").strip()
        for separator in ("|", ":", ";"):
            if separator in raw:
                login, password = [part.strip() for part in raw.split(separator, 1)]
                break
        else:
            parts = raw.split(maxsplit=1)
            if len(parts) != 2:
                await message.answer("Неверный формат. Используйте <code>login|password</code>.")
                return
            login, password = parts
        async with app.session_factory() as session:
            await add_capcut_account(session, login, password)
            await session.commit()
        await state.clear()
        await message.answer("Аккаунт добавлен.")

    @router.message(AdminState.waiting_stock_bulk)
    async def admin_stock_bulk_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        async with app.session_factory() as session:
            created = await add_bulk_accounts(session, message.text or "")
            await session.commit()
        await state.clear()
        await message.answer(f"Добавлено аккаунтов: <b>{created}</b>")

    def _product_detail_markup(product: Product) -> InlineKeyboardMarkup:
        toggle_text = "Выключить" if product.status == ProductStatus.ACTIVE else "Включить"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Цена", callback_data=f"admin:product:price:{product.id}"),
                    InlineKeyboardButton(text="Порядок", callback_data=f"admin:product:sort:{product.id}"),
                ],
                [
                    InlineKeyboardButton(text="Фото", callback_data=f"admin:product:photo:{product.id}"),
                    InlineKeyboardButton(text=toggle_text, callback_data=f"admin:product:toggle:{product.id}"),
                ],
                [
                    InlineKeyboardButton(text="RU", callback_data=f"admin:product:lang:{product.id}:ru"),
                    InlineKeyboardButton(text="UZ", callback_data=f"admin:product:lang:{product.id}:uz"),
                    InlineKeyboardButton(text="EN", callback_data=f"admin:product:lang:{product.id}:en"),
                ],
                [InlineKeyboardButton(text="Методы оплаты", callback_data=f"admin:product:payments:{product.id}")],
                [InlineKeyboardButton(text="Удалить", callback_data=f"admin:product:delete:{product.id}")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:products")],
            ]
        )

    def _payment_detail_markup(payment: PaymentMethod) -> InlineKeyboardMarkup:
        toggle_text = "Выключить" if payment.is_active else "Включить"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Реквизиты", callback_data=f"admin:payment:creds:{payment.id}"),
                    InlineKeyboardButton(text="Порядок", callback_data=f"admin:payment:sort:{payment.id}"),
                ],
                [
                    InlineKeyboardButton(text="Фото", callback_data=f"admin:payment:photo:{payment.id}"),
                    InlineKeyboardButton(text=toggle_text, callback_data=f"admin:payment:toggle:{payment.id}"),
                ],
                [
                    InlineKeyboardButton(text="RU", callback_data=f"admin:payment:lang:{payment.id}:ru"),
                    InlineKeyboardButton(text="UZ", callback_data=f"admin:payment:lang:{payment.id}:uz"),
                    InlineKeyboardButton(text="EN", callback_data=f"admin:payment:lang:{payment.id}:en"),
                ],
                [InlineKeyboardButton(text="Удалить", callback_data=f"admin:payment:delete:{payment.id}")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:payments")],
            ]
        )

    @router.callback_query(F.data == "admin:products")
    async def admin_products_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            products = list((await session.scalars(select(Product).order_by(Product.sort_order, Product.id))).all())
        await callback.answer()
        await answer_or_edit(callback, "<b>Товары</b>", reply_markup=_product_list_markup(products))

    @router.callback_query(F.data.regexp(r"^admin:product:\d+$"))
    async def admin_product_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            return
        product_id = int(parts[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
        await callback.answer()
        if product is None:
            await answer_or_edit(callback, "Товар не найден.", reply_markup=_back_main_markup())
            return
        ru_name = pick_translation(product.translations, "ru", "name") or product.code
        uz_name = pick_translation(product.translations, "uz", "name")
        en_name = pick_translation(product.translations, "en", "name")
        payment_names = ", ".join(link.payment_method.admin_title for link in product.payment_links) or "-"
        category_text = category_name(product.category, "ru") if product.category else "-"
        text = (
            f"<b>{ru_name}</b>\n\n"
            f"Code: <code>{product.code}</code>\n"
            f"Категория: {category_text}\n"
            f"RU: {ru_name}\n"
            f"UZ: {uz_name or '-'}\n"
            f"EN: {en_name or '-'}\n"
            f"Цена: <b>{format_money(product.price, product.currency)}</b>\n"
            f"Статус: <b>{product.status.value}</b>\n"
            f"Выдача: {product.delivery_type}\n"
            f"Workflow: {product.workflow_type}\n"
            f"Порядок: {product.sort_order}\n"
            f"Фото file_id: {product.photo_file_id or '-'}\n"
            f"Методы оплаты: {payment_names}"
        )
        await answer_or_edit(callback, text, reply_markup=_product_detail_markup(product))

    @router.callback_query(F.data == "admin:products:add")
    async def admin_products_add_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_create)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>code|category_code|price|currency|workflow_type|delivery_type</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:toggle:"))
    async def admin_product_toggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            if product is None:
                await callback.answer()
                return
            product.status = ProductStatus.HIDDEN if product.status == ProductStatus.ACTIVE else ProductStatus.ACTIVE
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:product:{product_id}"
        await admin_product_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:product:price:"))
    async def admin_product_price_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_price)
        await state.update_data(product_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новую цену.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:sort:"))
    async def admin_product_sort_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_sort)
        await state.update_data(product_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новый порядок.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:photo:"))
    async def admin_product_photo_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_product_photo)
        await state.update_data(product_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте фото товара.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:lang:"))
    async def admin_product_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, product_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_product_translation)
        await state.update_data(product_id=int(product_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>Название || Описание</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:product:payments:"))
    async def admin_product_payments_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            payments = list((await session.scalars(select(PaymentMethod).order_by(PaymentMethod.sort_order, PaymentMethod.id))).all())
        if product is None:
            await callback.answer()
            return
        attached = {link.payment_method_id for link in product.payment_links}
        rows = [[InlineKeyboardButton(text=f"{'✅' if payment.id in attached else '▫️'} {payment.admin_title}", callback_data=f"admin:product:paytoggle:{product.id}:{payment.id}")] for payment in payments]
        rows.append([InlineKeyboardButton(text="Назад", callback_data=f"admin:product:{product.id}")])
        await callback.answer()
        await answer_or_edit(callback, f"<b>Методы оплаты для {product_name(product, 'ru')}</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.callback_query(F.data.startswith("admin:product:paytoggle:"))
    async def admin_product_paytoggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, product_id, payment_id = callback.data.split(":")
        async with app.session_factory() as session:
            await toggle_product_payment_method(session, int(product_id), int(payment_id))
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:product:payments:{product_id}"
        await admin_product_payments_handler(callback)

    @router.callback_query(F.data.startswith("admin:product:delete:"))
    async def admin_product_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        product_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            product = await get_product(session, product_id)
            if product is None:
                await callback.answer()
                return
            await session.delete(product)
            await session.commit()
        await callback.answer("Удалено")
        await admin_products_handler(callback)

    @router.callback_query(F.data == "admin:payments")
    async def admin_payments_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            payments = list((await session.scalars(select(PaymentMethod).order_by(PaymentMethod.sort_order, PaymentMethod.id))).all())
        await callback.answer()
        await answer_or_edit(callback, "<b>Способы оплаты</b>", reply_markup=_payment_list_markup(payments))

    @router.callback_query(F.data.regexp(r"^admin:payment:\d+$"))
    async def admin_payment_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        parts = callback.data.split(":")
        if len(parts) != 3:
            return
        payment_id = int(parts[-1])
        async with app.session_factory() as session:
            payment = await get_payment_method(session, payment_id)
        if payment is None:
            await callback.answer()
            return
        text = (
            f"<b>{payment.admin_title}</b>\n\n"
            f"Code: <code>{payment.code}</code>\n"
            f"Тип: {payment.provider_type.value}\n"
            f"Реквизиты: <code>{payment.credentials or '-'}</code>\n"
            f"Статус: {'on' if payment.is_active else 'off'}\n"
            f"Порядок: {payment.sort_order}\n"
            f"Фото file_id: {payment.photo_file_id or '-'}\n"
            f"RU: {payment_title(payment, 'ru')}\n"
            f"UZ: {payment_title(payment, 'uz') or '-'}\n"
            f"EN: {payment_title(payment, 'en') or '-'}"
        )
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_payment_detail_markup(payment))

    @router.callback_query(F.data == "admin:payments:add")
    async def admin_payment_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_create)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>code|type|admin_title</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:toggle:"))
    async def admin_payment_toggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        payment_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            payment = await get_payment_method(session, payment_id)
            if payment is None:
                await callback.answer()
                return
            payment.is_active = not payment.is_active
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:payment:{payment_id}"
        await admin_payment_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:payment:creds:"))
    async def admin_payment_creds_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_credentials)
        await state.update_data(payment_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новые реквизиты.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:sort:"))
    async def admin_payment_sort_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_sort)
        await state.update_data(payment_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новый порядок.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:photo:"))
    async def admin_payment_photo_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_payment_photo)
        await state.update_data(payment_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте фото/QR для метода оплаты.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:lang:"))
    async def admin_payment_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, payment_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_payment_translation)
        await state.update_data(payment_id=int(payment_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>Название || Инструкция</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:payment:delete:"))
    async def admin_payment_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        payment_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            payment = await get_payment_method(session, payment_id)
            if payment is None:
                await callback.answer()
                return
            await session.delete(payment)
            await session.commit()
        await callback.answer("Удалено")
        await admin_payments_handler(callback)

    @router.callback_query(F.data == "admin:texts")
    @router.callback_query(F.data.startswith("admin:texts:"))
    async def admin_texts_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        page = int(callback.data.split(":")[-1]) if callback.data.count(":") == 2 else 0
        page_size = 10
        async with app.session_factory() as session:
            all_entries = list((await session.scalars(select(TextEntry).order_by(TextEntry.group_name, TextEntry.code))).all())
        total_pages = max((len(all_entries) + page_size - 1) // page_size, 1)
        page = min(max(page, 0), total_pages - 1)
        items = all_entries[page * page_size:(page + 1) * page_size]
        await callback.answer()
        await answer_or_edit(callback, "<b>Тексты</b>", reply_markup=_text_pages_markup(items, page, total_pages))

    @router.callback_query(F.data.regexp(r"^admin:text:\d+$"))
    async def admin_text_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        text_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            entry = await session.scalar(select(TextEntry).where(TextEntry.id == text_id))
        if entry is None:
            await callback.answer()
            return
        text = (
            f"<b>{entry.code}</b>\n\n"
            f"Группа: {entry.group_name}\n"
            f"Описание: {entry.description or '-'}\n\n"
            f"RU:\n{pick_translation(entry.translations, 'ru', 'value') or '-'}\n\n"
            f"UZ:\n{pick_translation(entry.translations, 'uz', 'value') or '-'}\n\n"
            f"EN:\n{pick_translation(entry.translations, 'en', 'value') or '-'}"
        )
        await callback.answer()
        await answer_or_edit(
            callback,
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="RU", callback_data=f"admin:text:lang:{entry.id}:ru"),
                        InlineKeyboardButton(text="UZ", callback_data=f"admin:text:lang:{entry.id}:uz"),
                        InlineKeyboardButton(text="EN", callback_data=f"admin:text:lang:{entry.id}:en"),
                    ],
                    [InlineKeyboardButton(text="Назад", callback_data="admin:texts")],
                ]
            ),
        )

    @router.callback_query(F.data.startswith("admin:text:lang:"))
    async def admin_text_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, text_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_text_translation)
        await state.update_data(text_id=int(text_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новое значение текста.", reply_markup=_back_main_markup())

    def _button_detail_markup(button: LayoutButton) -> InlineKeyboardMarkup:
        toggle_text = "Выключить" if button.is_active else "Включить"
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Назначение", callback_data=f"admin:button:action:{button.id}"),
                    InlineKeyboardButton(text="Ряд", callback_data=f"admin:button:row:{button.id}"),
                ],
                [
                    InlineKeyboardButton(text="Порядок", callback_data=f"admin:button:sort:{button.id}"),
                    InlineKeyboardButton(text="Цвет", callback_data=f"admin:button:style:{button.id}"),
                ],
                [
                    InlineKeyboardButton(text="RU", callback_data=f"admin:button:lang:{button.id}:ru"),
                    InlineKeyboardButton(text="UZ", callback_data=f"admin:button:lang:{button.id}:uz"),
                    InlineKeyboardButton(text="EN", callback_data=f"admin:button:lang:{button.id}:en"),
                ],
                [
                    InlineKeyboardButton(text=toggle_text, callback_data=f"admin:button:toggle:{button.id}"),
                    InlineKeyboardButton(text="Удалить", callback_data=f"admin:button:delete:{button.id}"),
                ],
                [InlineKeyboardButton(text="Назад", callback_data=f"admin:layout:{button.layout_id}")],
            ]
        )

    @router.callback_query(F.data == "admin:buttons")
    async def admin_buttons_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        async with app.session_factory() as session:
            layouts = await list_layouts(session)
        await callback.answer()
        await answer_or_edit(callback, "<b>Лейауты</b>", reply_markup=_layouts_markup(layouts))

    @router.callback_query(F.data.regexp(r"^admin:layout:\d+$"))
    async def admin_layout_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        layout_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            layout = await session.scalar(select(Layout).where(Layout.id == layout_id))
        if layout is None:
            await callback.answer()
            return
        rows = [[InlineKeyboardButton(text=f"{button.code} ({button.row_index}/{button.sort_order})", callback_data=f"admin:button:{button.id}")] for button in sorted(layout.buttons, key=lambda item: (item.row_index, item.sort_order, item.id))]
        rows.append([InlineKeyboardButton(text="Добавить кнопку", callback_data=f"admin:layout:add:{layout.id}")])
        rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:buttons")])
        await callback.answer()
        await answer_or_edit(callback, f"<b>{layout.title}</b>\nScope: {layout.scope}", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    @router.callback_query(F.data.startswith("admin:layout:add:"))
    async def admin_button_add_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_create)
        await state.update_data(layout_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>code|callback_or_url|action_value|row|sort|text_ru|text_uz|text_en</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.regexp(r"^admin:button:\d+$"))
    async def admin_button_detail_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
        if button is None:
            await callback.answer()
            return
        text = (
            f"<b>{button.code}</b>\n\n"
            f"Тип: {button.action_type.value}\n"
            f"Назначение: <code>{button.action_value}</code>\n"
            f"Ряд: {button.row_index}\n"
            f"Порядок: {button.sort_order}\n"
            f"Цвет: {button.style}\n"
            f"Активна: {button.is_active}\n\n"
            f"RU: {pick_translation(button.translations, 'ru', 'text') or '-'}\n"
            f"UZ: {pick_translation(button.translations, 'uz', 'text') or '-'}\n"
            f"EN: {pick_translation(button.translations, 'en', 'text') or '-'}"
        )
        await callback.answer()
        await answer_or_edit(callback, text, reply_markup=_button_detail_markup(button))

    @router.callback_query(F.data.startswith("admin:button:lang:"))
    async def admin_button_lang_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        _, _, _, button_id, lang = callback.data.split(":")
        await state.set_state(AdminState.waiting_button_translation)
        await state.update_data(button_id=int(button_id), language=lang)
        await callback.answer()
        await answer_or_edit(callback, "Отправьте новый текст кнопки.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:action:"))
    async def admin_button_action_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_action)
        await state.update_data(button_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте: <code>callback|action</code> или <code>url|https://...</code>", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:row:"))
    async def admin_button_row_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_row)
        await state.update_data(button_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте номер ряда.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:sort:"))
    async def admin_button_sort_prompt_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        await state.set_state(AdminState.waiting_button_sort)
        await state.update_data(button_id=int(callback.data.split(":")[-1]))
        await callback.answer()
        await answer_or_edit(callback, "Отправьте порядок сортировки.", reply_markup=_back_main_markup())

    @router.callback_query(F.data.startswith("admin:button:style:"))
    async def admin_button_style_cycle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        styles = ["default", "primary", "success", "danger"]
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
            if button is None:
                await callback.answer()
                return
            current_index = styles.index(button.style) if button.style in styles else 0
            button.style = styles[(current_index + 1) % len(styles)]
            await session.commit()
        await callback.answer("Цвет обновлён")
        callback.data = f"admin:button:{button_id}"
        await admin_button_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:button:toggle:"))
    async def admin_button_toggle_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
            if button is None:
                await callback.answer()
                return
            button.is_active = not button.is_active
            await session.commit()
        await callback.answer("Сохранено")
        callback.data = f"admin:button:{button_id}"
        await admin_button_detail_handler(callback)

    @router.callback_query(F.data.startswith("admin:button:delete:"))
    async def admin_button_delete_handler(callback: CallbackQuery) -> None:
        if not _guard(callback.from_user.id):
            await callback.answer()
            return
        button_id = int(callback.data.split(":")[-1])
        async with app.session_factory() as session:
            button = await get_button(session, button_id)
            if button is None:
                await callback.answer()
                return
            layout_id = button.layout_id
            await session.delete(button)
            await session.commit()
        await callback.answer("Удалено")
        callback.data = f"admin:layout:{layout_id}"
        await admin_layout_detail_handler(callback)

    @router.message(AdminState.waiting_product_create)
    async def admin_product_create_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 6:
            await message.answer("Неверный формат.")
            return
        code, category_code, price, currency, workflow_type, delivery_type = parts
        async with app.session_factory() as session:
            category = await session.scalar(select(Category).where(Category.code == category_code))
            product = Product(
                code=code,
                category_id=category.id if category else None,
                price=price,
                currency=currency,
                workflow_type=workflow_type,
                delivery_type=delivery_type,
                status=ProductStatus.HIDDEN,
                sort_order=100,
            )
            session.add(product)
            await session.flush()
            for lang in ("ru", "uz", "en"):
                session.add(ProductTranslation(product_id=product.id, language=Language(lang), name=code, description=""))
            await session.commit()
        await state.clear()
        await message.answer("Товар создан.")

    @router.message(AdminState.waiting_product_price)
    async def admin_product_price_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                return
            product.price = message.text.strip()
            await session.commit()
        await state.clear()
        await message.answer("Цена обновлена.")

    @router.message(AdminState.waiting_product_sort)
    async def admin_product_sort_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно целое число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                return
            product.sort_order = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Порядок обновлён.")

    @router.message(AdminState.waiting_product_translation)
    async def admin_product_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        name, _, description = (message.text or "").partition("||")
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(ProductTranslation).where(
                    ProductTranslation.product_id == int(data["product_id"]),
                    ProductTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод не найден.")
                return
            translation.name = name.strip() or translation.name
            translation.description = description.strip()
            await session.commit()
        await state.clear()
        await message.answer("Перевод товара обновлён.")

    @router.message(AdminState.waiting_product_photo, F.photo)
    async def admin_product_photo_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            product = await get_product(session, int(data["product_id"]))
            if product is None:
                await message.answer("Товар не найден.")
                return
            product.photo_file_id = message.photo[-1].file_id
            await session.commit()
        await state.clear()
        await message.answer("Фото товара обновлено.")

    @router.message(AdminState.waiting_payment_create)
    async def admin_payment_create_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 3:
            await message.answer("Неверный формат.")
            return
        code, provider_type, admin_title = parts
        async with app.session_factory() as session:
            payment = PaymentMethod(code=code, provider_type=PaymentProviderType(provider_type), admin_title=admin_title, credentials="", sort_order=100, is_active=True)
            session.add(payment)
            await session.flush()
            for lang in ("ru", "uz", "en"):
                session.add(PaymentMethodTranslation(payment_method_id=payment.id, language=Language(lang), title=admin_title, instructions="{credentials}"))
            await session.commit()
        await state.clear()
        await message.answer("Метод оплаты создан.")

    @router.message(AdminState.waiting_payment_credentials)
    async def admin_payment_credentials_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            payment = await get_payment_method(session, int(data["payment_id"]))
            if payment is None:
                await message.answer("Метод не найден.")
                return
            payment.credentials = message.text or ""
            await session.commit()
        await state.clear()
        await message.answer("Реквизиты обновлены.")

    @router.message(AdminState.waiting_payment_sort)
    async def admin_payment_sort_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            payment = await get_payment_method(session, int(data["payment_id"]))
            if payment is None:
                await message.answer("Метод не найден.")
                return
            payment.sort_order = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Порядок обновлён.")

    @router.message(AdminState.waiting_payment_translation)
    async def admin_payment_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        title, _, instructions = (message.text or "").partition("||")
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(PaymentMethodTranslation).where(
                    PaymentMethodTranslation.payment_method_id == int(data["payment_id"]),
                    PaymentMethodTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод не найден.")
                return
            translation.title = title.strip() or translation.title
            translation.instructions = instructions.strip() or translation.instructions
            await session.commit()
        await state.clear()
        await message.answer("Перевод оплаты обновлён.")

    @router.message(AdminState.waiting_payment_photo, F.photo)
    async def admin_payment_photo_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            payment = await get_payment_method(session, int(data["payment_id"]))
            if payment is None:
                await message.answer("Метод не найден.")
                return
            payment.photo_file_id = message.photo[-1].file_id
            await session.commit()
        await state.clear()
        await message.answer("Фото оплаты обновлено.")

    @router.message(AdminState.waiting_text_translation)
    async def admin_text_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(TextTranslation).where(
                    TextTranslation.text_id == int(data["text_id"]),
                    TextTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод не найден.")
                return
            translation.value = message.text or ""
            await session.commit()
        await state.clear()
        await message.answer("Текст обновлён.")

    @router.message(AdminState.waiting_button_create)
    async def admin_button_create_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        parts = [part.strip() for part in (message.text or "").split("|")]
        if len(parts) != 8:
            await message.answer("Неверный формат.")
            return
        code, action_type, action_value, row, sort, text_ru, text_uz, text_en = parts
        data = await state.get_data()
        async with app.session_factory() as session:
            button = LayoutButton(layout_id=int(data["layout_id"]), code=code, action_type=ButtonActionType(action_type), action_value=action_value, row_index=int(row), sort_order=int(sort), style="default", is_active=True)
            session.add(button)
            await session.flush()
            for lang, value in {"ru": text_ru, "uz": text_uz, "en": text_en}.items():
                session.add(LayoutButtonTranslation(button_id=button.id, language=Language(lang), text=value))
            await session.commit()
        await state.clear()
        await message.answer("Кнопка создана.")

    @router.message(AdminState.waiting_button_translation)
    async def admin_button_translation_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            translation = await session.scalar(
                select(LayoutButtonTranslation).where(
                    LayoutButtonTranslation.button_id == int(data["button_id"]),
                    LayoutButtonTranslation.language == data["language"],
                )
            )
            if translation is None:
                await message.answer("Перевод кнопки не найден.")
                return
            translation.text = message.text or ""
            await session.commit()
        await state.clear()
        await message.answer("Текст кнопки обновлён.")

    @router.message(AdminState.waiting_button_action)
    async def admin_button_action_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        raw = [part.strip() for part in (message.text or "").split("|", 1)]
        if len(raw) != 2:
            await message.answer("Используйте формат type|value.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            button = await get_button(session, int(data["button_id"]))
            if button is None:
                await message.answer("Кнопка не найдена.")
                return
            button.action_type = ButtonActionType(raw[0])
            button.action_value = raw[1]
            await session.commit()
        await state.clear()
        await message.answer("Назначение кнопки обновлено.")

    @router.message(AdminState.waiting_button_row)
    async def admin_button_row_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            button = await get_button(session, int(data["button_id"]))
            if button is None:
                await message.answer("Кнопка не найдена.")
                return
            button.row_index = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Ряд кнопки обновлён.")

    @router.message(AdminState.waiting_button_sort)
    async def admin_button_sort_message_handler(message: Message, state: FSMContext) -> None:
        if not _guard(message.from_user.id):
            return
        if not (message.text or "").strip().isdigit():
            await message.answer("Нужно число.")
            return
        data = await state.get_data()
        async with app.session_factory() as session:
            button = await get_button(session, int(data["button_id"]))
            if button is None:
                await message.answer("Кнопка не найдена.")
                return
            button.sort_order = int(message.text.strip())
            await session.commit()
        await state.clear()
        await message.answer("Порядок кнопки обновлён.")

    return router
