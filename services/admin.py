from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import OrderStatus, ProductStatus
from db.models import CapCutAccount, Order, PaymentMethod, Product, TextEntry, User
from services.capcut import purge_expired_accounts


async def build_stats_text(session: AsyncSession) -> str:
    if await purge_expired_accounts(session):
        await session.commit()

    users_total = await session.scalar(select(func.count(User.id))) or 0
    orders_total = await session.scalar(select(func.count(Order.id))) or 0
    waiting_check = await session.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.WAITING_CHECK)) or 0
    processing = await session.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.PROCESSING)) or 0
    completed = await session.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED)) or 0
    active_products = await session.scalar(select(func.count(Product.id)).where(Product.status == ProductStatus.ACTIVE)) or 0
    payment_methods = await session.scalar(select(func.count(PaymentMethod.id))) or 0
    free_capcut = await session.scalar(select(func.count(CapCutAccount.id)).where(CapCutAccount.is_used.is_(False))) or 0
    texts_total = await session.scalar(select(func.count(TextEntry.id))) or 0

    return (
        "<b>Статистика</b>\n\n"
        f"Пользователи: <b>{users_total}</b>\n"
        f"Заказы: <b>{orders_total}</b>\n"
        f"На проверке: <b>{waiting_check}</b>\n"
        f"В работе: <b>{processing}</b>\n"
        f"Завершено: <b>{completed}</b>\n"
        f"Активных товаров: <b>{active_products}</b>\n"
        f"Методов оплаты: <b>{payment_methods}</b>\n"
        f"Свободных CapCut аккаунтов: <b>{free_capcut}</b>\n"
        f"Текстовых ключей: <b>{texts_total}</b>"
    )
