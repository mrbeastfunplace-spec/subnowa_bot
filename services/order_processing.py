from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from db.base import OrderStatus
from db.models import CapCutAccount, Order
from services.capcut import claim_free_account
from services.orders import change_status
from services.users import get_user_language
from utils.formatting import user_display_name


def admin_open_order_markup(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть заказ", callback_data=f"admin:order:{order_id}")]]
    )


def _user_button_texts(language: str) -> dict[str, str]:
    if language == "uz":
        return {
            "details": "📄 Buyurtma tafsilotlari",
            "support": "💬 Yordam",
            "reviews": "💬 Fikrlar",
            "menu": "🏠 Menu",
        }
    if language == "en":
        return {
            "details": "📄 Order details",
            "support": "💬 Support",
            "reviews": "💬 Reviews",
            "menu": "🏠 Menu",
        }
    return {
        "details": "📄 Детали заказа",
        "support": "💬 Поддержка",
        "reviews": "💬 Отзывы",
        "menu": "🏠 Меню",
    }


def user_order_markup(settings: Settings, language: str, order: Order) -> InlineKeyboardMarkup:
    labels = _user_button_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=labels["details"], callback_data=f"order:detail:{order.id}")],
            [InlineKeyboardButton(text=labels["support"], url=settings.support_url)],
            [InlineKeyboardButton(text=labels["reviews"], url=settings.review_url)],
            [InlineKeyboardButton(text=labels["menu"], callback_data="menu:main")],
        ]
    )


def user_menu_markup(settings: Settings, language: str) -> InlineKeyboardMarkup:
    labels = _user_button_texts(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=labels["support"], url=settings.support_url)],
            [InlineKeyboardButton(text=labels["menu"], callback_data="menu:main")],
        ]
    )


async def send_user_message(bot: Bot, telegram_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await bot.send_message(telegram_id, text, reply_markup=reply_markup)
    except Exception:
        pass


async def resolve_user_language(session: AsyncSession, settings: Settings, order: Order) -> str:
    if order.user is None:
        return order.language or settings.default_language
    return await get_user_language(session, order.user.telegram_id, settings.default_language)


def paid_notice(language: str, order: Order) -> str:
    if order.product_code_snapshot == "chatgpt_plus_month":
        order_no = escape(order.order_number)
        separator = "──────────────────────"
        if language == "uz":
            return (
                "🎉 Buyurtma tayyor\n\n"
                f"Buyurtma: {order_no}\n"
                "Mahsulot: ChatGPT PLUS (1 oy)\n\n"
                f"{separator}\n\n"
                "biz havolani emailingizga yubordik, tasdiqlagandan so‘ng sizga 30 kunlik PLUS versiya mavjud bo‘ladi\n\n"
                f"{separator}"
            )
        if language == "en":
            return (
                "🎉 Order completed\n\n"
                f"Order: {order_no}\n"
                "Product: ChatGPT PLUS (1 month)\n\n"
                f"{separator}\n\n"
                "we have sent a link to your email, after confirmation you will get 30 days of ChatGPT PLUS\n\n"
                f"{separator}"
            )
        return (
            "🎉 Заказ готов\n\n"
            f"Заказ: {order_no}\n"
            "Товар: ChatGPT PLUS (1 месяц)\n\n"
            f"{separator}\n\n"
            "мы отправили ссылку на вашу почту, после подтвеждение вам будет доступно 30 дней PLUS версия ChatGPT\n\n"
            f"{separator}"
        )

    product_name = escape(order.product_name_snapshot)
    order_no = escape(order.order_number)
    if language == "uz":
        return (
            "✅ To'lov qabul qilindi\n\n"
            f"Buyurtma: <code>{order_no}</code>\n"
            f"Mahsulot: {product_name}\n"
            "Holat: paid\n\n"
            "To'lov muvaffaqiyatli qabul qilindi. Buyurtma holati avtomatik yangilandi."
        )
    if language == "en":
        return (
            "✅ Payment received\n\n"
            f"Order: <code>{order_no}</code>\n"
            f"Product: {product_name}\n"
            "Status: paid\n\n"
            "Your payment was received successfully and the order status was updated automatically."
        )
    return (
        "✅ Оплата получена\n\n"
        f"Заказ: <code>{order_no}</code>\n"
        f"Товар: {product_name}\n"
        "Статус: paid\n\n"
        "Оплата прошла успешно, статус заказа обновлён автоматически."
    )


def processing_notice(language: str, order: Order) -> str:
    product_name = escape(order.product_name_snapshot)
    order_no = escape(order.order_number)
    if language == "uz":
        return (
            "✅ To'lov tasdiqlandi\n\n"
            f"Buyurtma: <code>{order_no}</code>\n"
            f"Mahsulot: {product_name}\n"
            "Holat: ishlovga o'tkazildi\n\n"
            "To'lovingiz qabul qilindi va buyurtma ishga olindi. Hozir jamoamiz ulanishni tayyorlamoqda.\n\n"
            "Hammasi tayyor bo'lishi bilan shu botda alohida xabar yuboramiz."
        )
    if language == "en":
        return (
            "✅ Payment confirmed\n\n"
            f"Order: <code>{order_no}</code>\n"
            f"Product: {product_name}\n"
            "Status: in progress\n\n"
            "We received your payment and started processing the order. Our team is preparing the activation now.\n\n"
            "You will get a separate message in this bot as soon as everything is ready."
        )
    return (
        "✅ Оплата подтверждена\n\n"
        f"Заказ: <code>{order_no}</code>\n"
        f"Товар: {product_name}\n"
        "Статус: передан в работу\n\n"
        "Мы получили ваш платёж и уже начали обработку заказа. Сейчас готовим подключение.\n\n"
        "Как только всё будет готово, сразу отправим отдельное сообщение в этом боте."
    )


def completed_notice(language: str, order: Order) -> str:
    product_name = escape(order.product_name_snapshot)
    order_no = escape(order.order_number)
    if language == "uz":
        return (
            "🎉 Buyurtma tayyor\n\n"
            f"Buyurtma: <code>{order_no}</code>\n"
            f"Mahsulot: {product_name}\n\n"
            "Ulanish muvaffaqiyatli yakunlandi. Agar faollashtirishdan keyin savollar qolsa, shu botdagi yordam bo'limi orqali yozing."
        )
    if language == "en":
        return (
            "🎉 Order completed\n\n"
            f"Order: <code>{order_no}</code>\n"
            f"Product: {product_name}\n\n"
            "Activation is complete. If you need anything after that, contact support from this bot."
        )
    return (
        "🎉 Заказ готов\n\n"
        f"Заказ: <code>{order_no}</code>\n"
        f"Товар: {product_name}\n\n"
        "Подключение завершено. Если после активации появятся вопросы, напишите в поддержку через этого бота."
    )


def rejected_notice(language: str, order: Order) -> str:
    order_no = escape(order.order_number)
    if language == "uz":
        return (
            "❌ Buyurtma rad etildi\n\n"
            f"Buyurtma: <code>{order_no}</code>\n"
            "Agar bu xato bo'lsa, yordam xizmatiga murojaat qiling."
        )
    if language == "en":
        return (
            "❌ Order rejected\n\n"
            f"Order: <code>{order_no}</code>\n"
            "If this happened by mistake, please contact support."
        )
    return (
        "❌ Заказ отклонён\n\n"
        f"Заказ: <code>{order_no}</code>\n"
        "Если это произошло по ошибке, пожалуйста, свяжитесь с поддержкой."
    )


def capcut_waiting_notice(language: str, order: Order) -> str:
    product_name = escape(order.product_name_snapshot)
    order_no = escape(order.order_number)
    if language == "uz":
        return (
            "✅ To'lov tasdiqlandi\n\n"
            f"Buyurtma: <code>{order_no}</code>\n"
            f"Mahsulot: {product_name}\n\n"
            "To'lov qabul qilindi, lekin hozir CapCut uchun bo'sh akkaunt qolmagan. Buyurtmangiz ishlovda qoldi.\n\n"
            "Bo'sh akkaunt paydo bo'lishi bilan ma'lumotlarni shu botga yuboramiz."
        )
    if language == "en":
        return (
            "✅ Payment confirmed\n\n"
            f"Order: <code>{order_no}</code>\n"
            f"Product: {product_name}\n\n"
            "Your payment is confirmed, but there are no free CapCut accounts right now. The order remains in progress.\n\n"
            "We will send the account details here as soon as stock appears."
        )
    return (
        "✅ Оплата подтверждена\n\n"
        f"Заказ: <code>{order_no}</code>\n"
        f"Товар: {product_name}\n\n"
        "Платёж подтверждён, но сейчас нет свободного аккаунта CapCut. Заказ оставлен в работе.\n\n"
        "Как только появится свободный аккаунт, сразу отправим данные в этот бот."
    )


def capcut_ready_notice(language: str, order: Order, account: CapCutAccount) -> str:
    order_no = escape(order.order_number)
    login = escape(account.login)
    password = escape(account.password)
    if language == "uz":
        return (
            "✅ To'lov tasdiqlandi\n\n"
            "🎬 CapCut Pro tayyor.\n"
            f"Buyurtma: <code>{order_no}</code>\n"
            f"Login: <code>{login}</code>\n"
            f"Parol: <code>{password}</code>\n\n"
            "Agar boshqa CapCut akkaunti ochiq bo'lsa, avval undan chiqing, keyin yuqoridagi ma'lumotlar bilan kiring."
        )
    if language == "en":
        return (
            "✅ Payment confirmed\n\n"
            "🎬 Your CapCut Pro is ready.\n"
            f"Order: <code>{order_no}</code>\n"
            f"Login: <code>{login}</code>\n"
            f"Password: <code>{password}</code>\n\n"
            "If another CapCut account is currently open, sign out first and then sign in with the credentials above."
        )
    return (
        "✅ Оплата подтверждена\n\n"
        "🎬 Ваш CapCut Pro готов.\n"
        f"Заказ: <code>{order_no}</code>\n"
        f"Логин: <code>{login}</code>\n"
        f"Пароль: <code>{password}</code>\n\n"
        "Если у вас уже открыт другой аккаунт CapCut, сначала выйдите из него, а затем войдите по данным выше."
    )


async def notify_admins_paid(bot: Bot, settings: Settings, order: Order) -> None:
    user_name = escape(user_display_name(order.user, order.user.telegram_id if order.user else None))
    gmail = escape(str((order.details or {}).get("gmail", "-")))
    text = (
        "✅ Оплата получена\n\n"
        f"Заказ: <code>{escape(order.order_number)}</code>\n"
        f"Пользователь: <b>{user_name}</b>\n"
        f"Товар: {escape(order.product_name_snapshot)}\n"
        f"Gmail: {gmail}\n"
        f"Статус заказа: <b>{order.status.value}</b>"
    )
    markup = admin_open_order_markup(order.id)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception:
            continue


async def mark_order_paid(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    order: Order,
    *,
    note: str,
) -> Order:
    if order.user is None:
        return order

    language = await resolve_user_language(session, settings, order)

    if order.workflow_type == "capcut_auto":
        if order.status == OrderStatus.COMPLETED and order.capcut_account is not None:
            return order
        account = order.capcut_account or await claim_free_account(session, order)
        if account is None:
            if order.status != OrderStatus.PROCESSING:
                await change_status(session, order, OrderStatus.PROCESSING, note=note)
                await session.commit()
                await send_user_message(bot, order.user.telegram_id, capcut_waiting_notice(language, order), reply_markup=user_order_markup(settings, language, order))
                await notify_admins_paid(bot, settings, order)
            return order
        if order.status != OrderStatus.COMPLETED:
            await change_status(session, order, OrderStatus.COMPLETED, note=note)
            await session.commit()
            await send_user_message(bot, order.user.telegram_id, capcut_ready_notice(language, order, account), reply_markup=user_order_markup(settings, language, order))
            await notify_admins_paid(bot, settings, order)
        return order

    if order.status in {OrderStatus.PROCESSING, OrderStatus.COMPLETED}:
        return order

    if order.status != OrderStatus.PAID:
        await change_status(session, order, OrderStatus.PAID, note=note)
        await session.commit()
        await send_user_message(bot, order.user.telegram_id, paid_notice(language, order), reply_markup=user_order_markup(settings, language, order))
        await notify_admins_paid(bot, settings, order)
    return order


async def approve_order_by_admin(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    order: Order,
    *,
    changed_by_telegram_id: int | None,
) -> Order:
    if order.user is None:
        return order

    language = await resolve_user_language(session, settings, order)
    if order.status in {OrderStatus.PAID, OrderStatus.PROCESSING}:
        if order.workflow_type == "capcut_auto":
            account = order.capcut_account or await claim_free_account(session, order)
            if account is None:
                raise RuntimeError("capcut_stock_empty")
            await change_status(session, order, OrderStatus.COMPLETED, changed_by_telegram_id, "confirmed by admin")
            await session.commit()
            await send_user_message(bot, order.user.telegram_id, capcut_ready_notice(language, order, account), reply_markup=user_order_markup(settings, language, order))
            return order
        await change_status(session, order, OrderStatus.COMPLETED, changed_by_telegram_id, "completed by admin")
        await session.commit()
        await send_user_message(bot, order.user.telegram_id, completed_notice(language, order), reply_markup=user_order_markup(settings, language, order))
        return order

    if order.workflow_type == "capcut_auto":
        account = await claim_free_account(session, order)
        if account is None:
            await change_status(session, order, OrderStatus.PROCESSING, changed_by_telegram_id, "payment approved, stock empty")
            await session.commit()
            await send_user_message(bot, order.user.telegram_id, capcut_waiting_notice(language, order), reply_markup=user_order_markup(settings, language, order))
            return order
        await change_status(session, order, OrderStatus.COMPLETED, changed_by_telegram_id, "auto issued capcut account")
        await session.commit()
        await send_user_message(bot, order.user.telegram_id, capcut_ready_notice(language, order, account), reply_markup=user_order_markup(settings, language, order))
        return order

    await change_status(session, order, OrderStatus.PROCESSING, changed_by_telegram_id, "payment approved")
    await session.commit()
    await send_user_message(bot, order.user.telegram_id, processing_notice(language, order), reply_markup=user_order_markup(settings, language, order))
    return order


async def reject_order_by_admin(
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    order: Order,
    *,
    changed_by_telegram_id: int | None,
) -> Order:
    if order.user is None:
        return order

    language = await resolve_user_language(session, settings, order)
    await change_status(session, order, OrderStatus.REJECTED, changed_by_telegram_id, "rejected by admin")
    await session.commit()
    await send_user_message(bot, order.user.telegram_id, rejected_notice(language, order), reply_markup=user_menu_markup(settings, language))
    return order
