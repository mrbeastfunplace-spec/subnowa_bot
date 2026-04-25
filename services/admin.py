from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import OrderStatus, TopupStatus
from db.models import Order, Topup, User
from utils.formatting import format_money


def _sum_or_zero(value: Decimal | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


async def build_stats_text(session: AsyncSession) -> str:
    users_total = await session.scalar(select(func.count(User.id))) or 0
    total_balance = _sum_or_zero(await session.scalar(select(func.sum(User.balance))))
    orders_total = await session.scalar(select(func.count(Order.id))) or 0
    completed_orders = (
        await session.scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.COMPLETED))
        or 0
    )
    processing_orders = (
        await session.scalar(
            select(func.count(Order.id)).where(Order.status.in_([OrderStatus.PROCESSING, OrderStatus.WAITING]))
        )
        or 0
    )
    pending_topups = (
        await session.scalar(select(func.count(Topup.id)).where(Topup.status == TopupStatus.PENDING))
        or 0
    )
    total_topups = _sum_or_zero(
        await session.scalar(select(func.sum(Topup.amount)).where(Topup.status == TopupStatus.APPROVED))
    )
    total_sales = _sum_or_zero(
        await session.scalar(
            select(func.sum(Order.amount)).where(
                Order.status.in_([OrderStatus.PAID, OrderStatus.PROCESSING, OrderStatus.WAITING, OrderStatus.COMPLETED])
            )
        )
    )

    return (
        "<b>📊 Статистика бота</b>\n\n"
        f"👤 Пользователей: {users_total}\n"
        f"💰 Общий баланс пользователей: {format_money(total_balance, 'сум')}\n"
        f"🛒 Заказов всего: {orders_total}\n"
        f"✅ Выполнено заказов: {completed_orders}\n"
        f"⏳ В обработке: {processing_orders}\n"
        f"📥 Пополнений ожидает: {pending_topups}\n"
        f"💵 Пополнено всего: {format_money(total_topups, 'сум')}\n"
        f"💸 Продаж всего: {format_money(total_sales, 'сум')}"
    )
