from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import utcnow
from db.models import CapCutAccount, Order


async def count_free_accounts(session: AsyncSession) -> int:
    result = await session.scalars(
        select(CapCutAccount).where(CapCutAccount.is_used.is_(False))
    )
    return len(result.all())


async def add_capcut_account(session: AsyncSession, login: str, password: str) -> CapCutAccount:
    row = CapCutAccount(login=login.strip(), password=password.strip())
    session.add(row)
    await session.flush()
    return row


async def add_bulk_accounts(session: AsyncSession, raw_value: str) -> int:
    count = 0
    for line in raw_value.splitlines():
        line = line.strip()
        if not line:
            continue
        for separator in ("|", ":", ";"):
            if separator in line:
                login, password = [part.strip() for part in line.split(separator, 1)]
                break
        else:
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            login, password = parts
        if login and password:
            await add_capcut_account(session, login, password)
            count += 1
    return count


async def list_accounts(session: AsyncSession, used: bool | None = None, limit: int = 30) -> list[CapCutAccount]:
    stmt = select(CapCutAccount)
    if used is not None:
        stmt = stmt.where(CapCutAccount.is_used.is_(used))
    stmt = stmt.order_by(desc(CapCutAccount.created_at), desc(CapCutAccount.id)).limit(limit)
    result = await session.scalars(stmt)
    return list(result.all())


async def claim_free_account(session: AsyncSession, order: Order) -> CapCutAccount | None:
    result = await session.scalars(
        select(CapCutAccount)
        .where(CapCutAccount.is_used.is_(False))
        .order_by(CapCutAccount.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    account = result.first()
    if account is None:
        return None
    account.is_used = True
    account.issued_order_id = order.id
    account.issued_to_user_id = order.user_id
    account.issued_at = utcnow()
    await session.flush()
    return account
