from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Setting


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    row = await session.scalar(select(Setting).where(Setting.key == key))
    return row.value if row else default


async def set_setting(
    session: AsyncSession,
    key: str,
    value: str,
    value_type: str = "string",
    description: str | None = None,
) -> Setting:
    row = await session.scalar(select(Setting).where(Setting.key == key))
    if row is None:
        row = Setting(key=key)
        session.add(row)
    row.value = value
    row.value_type = value_type
    if description is not None:
        row.description = description
    await session.flush()
    return row
