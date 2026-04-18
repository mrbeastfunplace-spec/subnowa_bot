from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import BroadcastButtonType, BroadcastKind, BroadcastStatus
from db.models import Broadcast


async def get_broadcast(session: AsyncSession, broadcast_id: int) -> Broadcast | None:
    return await session.scalar(select(Broadcast).where(Broadcast.id == broadcast_id))


async def list_broadcasts(session: AsyncSession, limit: int = 10) -> list[Broadcast]:
    result = await session.scalars(
        select(Broadcast).order_by(desc(Broadcast.created_at), desc(Broadcast.id)).limit(limit)
    )
    return list(result.all())


async def save_broadcast_draft(
    session: AsyncSession,
    *,
    broadcast_id: int | None,
    broadcast_type: BroadcastKind,
    message_text: str,
    photo_file_id: str | None,
    button_type: BroadcastButtonType,
    button_text: str | None,
    button_value: str | None,
    created_by_admin_telegram_id: int,
) -> Broadcast:
    broadcast = await get_broadcast(session, broadcast_id) if broadcast_id else None
    if broadcast is None:
        broadcast = Broadcast(
            created_by_admin_telegram_id=created_by_admin_telegram_id,
            broadcast_type=broadcast_type,
        )
        session.add(broadcast)

    broadcast.broadcast_type = broadcast_type
    broadcast.message_text = message_text
    broadcast.photo_file_id = photo_file_id
    broadcast.button_type = button_type
    broadcast.button_text = button_text
    broadcast.button_value = button_value
    if broadcast.status == BroadcastStatus.CANCELLED:
        broadcast.status = BroadcastStatus.DRAFT
    await session.flush()
    return broadcast
