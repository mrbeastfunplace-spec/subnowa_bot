from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import CheckoutSessionStatus, utcnow
from db.models import CheckoutSession, Product, User


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def create_checkout_session(
    session: AsyncSession,
    *,
    user: User,
    product: Product,
    payload: dict | None = None,
) -> CheckoutSession:
    amount = _to_decimal(product.price or 0)
    balance_before = _to_decimal(user.balance or 0)
    checkout = CheckoutSession(
        user_id=user.id,
        product_id=product.id,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_before - amount,
        status=CheckoutSessionStatus.PENDING,
        payload=payload or {},
    )
    session.add(checkout)
    await session.flush()
    return checkout


async def get_checkout_session(session: AsyncSession, checkout_id: int) -> CheckoutSession | None:
    return await session.scalar(select(CheckoutSession).where(CheckoutSession.id == checkout_id))


async def claim_checkout_processing(session: AsyncSession, checkout_id: int) -> bool:
    result = await session.execute(
        update(CheckoutSession)
        .where(
            CheckoutSession.id == checkout_id,
            CheckoutSession.status == CheckoutSessionStatus.PENDING,
        )
        .values(status=CheckoutSessionStatus.PROCESSING)
    )
    await session.flush()
    return (result.rowcount or 0) > 0


async def complete_checkout_session(
    session: AsyncSession,
    checkout: CheckoutSession,
    *,
    order_id: int,
) -> CheckoutSession:
    checkout.order_id = order_id
    checkout.status = CheckoutSessionStatus.COMPLETED
    checkout.processed_at = utcnow()
    await session.flush()
    return checkout


async def cancel_checkout_session(session: AsyncSession, checkout: CheckoutSession) -> CheckoutSession:
    checkout.status = CheckoutSessionStatus.CANCELLED
    checkout.processed_at = utcnow()
    await session.flush()
    return checkout
