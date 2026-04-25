from __future__ import annotations

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import Language, OrderStatus, utcnow
from db.models import Order, User
from services.texts import normalize_language


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id))


async def find_users(session: AsyncSession, query: str, limit: int = 10) -> list[User]:
    normalized = (query or "").strip()
    if not normalized:
        return []
    conditions = []
    if normalized.isdigit():
        numeric = int(normalized)
        conditions.extend([User.id == numeric, User.telegram_id == numeric])
    like_value = f"%{normalized.lstrip('@')}%"
    conditions.extend(
        [
            User.username.ilike(like_value),
            User.full_name.ilike(like_value),
            User.first_name.ilike(like_value),
        ]
    )
    result = await session.scalars(
        select(User)
        .where(or_(*conditions))
        .order_by(desc(User.created_at), desc(User.id))
        .limit(limit)
    )
    return list(result.all())


async def upsert_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    full_name: str,
    default_language: str = "ru",
    first_name: str | None = None,
) -> tuple[User, bool]:
    user = await get_user_by_telegram_id(session, telegram_id)
    is_new = user is None
    normalized_first_name = (first_name or (full_name or "").split(" ", 1)[0]).strip()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=normalized_first_name,
            full_name=full_name or "",
            language=Language(normalize_language(default_language)),
            language_selected=False,
        )
        session.add(user)
    else:
        user.username = username
        user.first_name = normalized_first_name or user.first_name or ""
        user.full_name = full_name or user.full_name or ""
    await session.flush()
    return user, is_new


async def touch_user(session: AsyncSession, telegram_id: int) -> None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user:
        user.last_seen_at = utcnow()


async def set_user_language(session: AsyncSession, telegram_id: int, language: str) -> User | None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    user.language = Language(normalize_language(language))
    user.language_selected = True
    await session.flush()
    return user


async def get_user_language(session: AsyncSession, telegram_id: int, default: str = "ru") -> str:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return default
    return normalize_language(user.language.value if user.language else None, default=default)


async def list_completed_orders_for_user(session: AsyncSession, user_id: int) -> list[Order]:
    result = await session.scalars(
        select(Order)
        .where(Order.user_id == user_id, Order.status == OrderStatus.COMPLETED)
        .order_by(desc(Order.created_at))
    )
    return list(result.all())


async def count_orders_for_user(session: AsyncSession, user_id: int) -> int:
    return await session.scalar(select(func.count(Order.id)).where(Order.user_id == user_id)) or 0


async def user_has_trial(session: AsyncSession, user_id: int) -> bool:
    result = await session.scalars(
        select(Order).where(Order.user_id == user_id, Order.workflow_type == "trial").limit(1)
    )
    return result.first() is not None


async def get_last_chatgpt_gmail(session: AsyncSession, user_id: int) -> str:
    result = await session.scalars(
        select(Order)
        .where(Order.user_id == user_id, Order.workflow_type.in_(["chatgpt_manual", "trial"]))
        .order_by(desc(Order.created_at))
        .limit(20)
    )
    for order in result.all():
        gmail = (order.details or {}).get("gmail", "").strip()
        if gmail:
            return gmail
    return ""
