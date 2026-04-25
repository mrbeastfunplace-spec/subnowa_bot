from __future__ import annotations

from decimal import Decimal

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import TopupStatus, utcnow
from db.models import Topup, User


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def create_topup(
    session: AsyncSession,
    *,
    user: User,
    amount: Decimal | int | float | str,
    payment_method: str,
    receipt_file_id: str,
    receipt_file_type: str,
) -> Topup:
    topup = Topup(
        user_id=user.id,
        amount=_to_decimal(amount),
        payment_method=payment_method,
        status=TopupStatus.PENDING,
        receipt_file_id=receipt_file_id,
        receipt_file_type=receipt_file_type,
    )
    session.add(topup)
    await session.flush()
    return topup


async def get_topup_by_id(session: AsyncSession, topup_id: int) -> Topup | None:
    return await session.scalar(select(Topup).where(Topup.id == topup_id))


async def list_pending_topups(session: AsyncSession) -> list[Topup]:
    result = await session.scalars(
        select(Topup)
        .where(Topup.status == TopupStatus.PENDING)
        .order_by(Topup.created_at, Topup.id)
    )
    return list(result.all())


async def list_user_topups(session: AsyncSession, user_id: int, limit: int = 20) -> list[Topup]:
    result = await session.scalars(
        select(Topup)
        .where(Topup.user_id == user_id)
        .order_by(desc(Topup.created_at), desc(Topup.id))
        .limit(limit)
    )
    return list(result.all())


async def approve_topup(session: AsyncSession, topup: Topup, admin_id: int) -> Topup:
    topup.status = TopupStatus.APPROVED
    topup.admin_id = admin_id
    topup.approved_at = utcnow()
    await session.flush()
    return topup


async def reject_topup(session: AsyncSession, topup: Topup, admin_id: int) -> Topup:
    topup.status = TopupStatus.REJECTED
    topup.admin_id = admin_id
    topup.approved_at = utcnow()
    await session.flush()
    return topup
