from __future__ import annotations

from decimal import Decimal

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import BalanceTransactionType
from db.models import BalanceTransaction, User


def _to_decimal(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def get_user_balance(session: AsyncSession, user_id: int) -> Decimal:
    balance = await session.scalar(select(User.balance).where(User.id == user_id))
    return _to_decimal(balance or 0)


async def list_balance_transactions(session: AsyncSession, user_id: int, limit: int = 10) -> list[BalanceTransaction]:
    result = await session.scalars(
        select(BalanceTransaction)
        .where(BalanceTransaction.user_id == user_id)
        .order_by(desc(BalanceTransaction.created_at), desc(BalanceTransaction.id))
        .limit(limit)
    )
    return list(result.all())


async def add_balance_transaction(
    session: AsyncSession,
    *,
    user_id: int,
    tx_type: BalanceTransactionType,
    amount: Decimal | int | float | str,
    balance_before: Decimal | int | float | str,
    balance_after: Decimal | int | float | str,
    source: str | None = None,
    source_id: int | None = None,
) -> BalanceTransaction:
    transaction = BalanceTransaction(
        user_id=user_id,
        type=tx_type,
        amount=_to_decimal(amount),
        balance_before=_to_decimal(balance_before),
        balance_after=_to_decimal(balance_after),
        source=source,
        source_id=source_id,
    )
    session.add(transaction)
    await session.flush()
    return transaction


async def credit_balance(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal | int | float | str,
    tx_type: BalanceTransactionType,
    source: str | None = None,
    source_id: int | None = None,
) -> BalanceTransaction:
    amount_dec = _to_decimal(amount)
    result = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(balance=User.balance + amount_dec)
        .returning(User.balance)
    )
    balance_after = result.scalar_one()
    balance_before = _to_decimal(balance_after) - amount_dec
    return await add_balance_transaction(
        session,
        user_id=user_id,
        tx_type=tx_type,
        amount=amount_dec,
        balance_before=balance_before,
        balance_after=balance_after,
        source=source,
        source_id=source_id,
    )


async def debit_balance(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal | int | float | str,
    tx_type: BalanceTransactionType,
    source: str | None = None,
    source_id: int | None = None,
) -> BalanceTransaction | None:
    amount_dec = _to_decimal(amount)
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.balance >= amount_dec)
        .values(balance=User.balance - amount_dec)
        .returning(User.balance)
    )
    balance_after = result.scalar_one_or_none()
    if balance_after is None:
        return None
    balance_before = _to_decimal(balance_after) + amount_dec
    return await add_balance_transaction(
        session,
        user_id=user_id,
        tx_type=tx_type,
        amount=-amount_dec,
        balance_before=balance_before,
        balance_after=balance_after,
        source=source,
        source_id=source_id,
    )


async def apply_admin_adjustment(
    session: AsyncSession,
    *,
    user_id: int,
    delta: Decimal | int | float | str,
    source: str = "admin_adjustment",
    source_id: int | None = None,
) -> BalanceTransaction | None:
    delta_dec = _to_decimal(delta)
    if delta_dec == 0:
        return None
    if delta_dec > 0:
        return await credit_balance(
            session,
            user_id=user_id,
            amount=delta_dec,
            tx_type=BalanceTransactionType.ADMIN_ADJUSTMENT,
            source=source,
            source_id=source_id,
        )
    return await debit_balance(
        session,
        user_id=user_id,
        amount=abs(delta_dec),
        tx_type=BalanceTransactionType.ADMIN_ADJUSTMENT,
        source=source,
        source_id=source_id,
    )
