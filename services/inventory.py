from __future__ import annotations

from collections import Counter

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import InventoryStatus, utcnow
from db.models import InventoryItem, Product


def inventory_delivery_text(item: InventoryItem) -> str:
    parts = []
    if (item.title or "").strip():
        parts.append(item.title.strip())
    if (item.content or "").strip():
        parts.append(item.content.strip())
    if (item.instruction or "").strip():
        parts.append(f"Инструкция:\n{item.instruction.strip()}")
    return "\n\n".join(parts).strip()


async def get_inventory_item(session: AsyncSession, item_id: int) -> InventoryItem | None:
    return await session.scalar(select(InventoryItem).where(InventoryItem.id == item_id))


async def list_inventory_products(session: AsyncSession) -> list[Product]:
    result = await session.scalars(
        select(Product)
        .where(Product.product_type == "ready_access")
        .order_by(Product.sort_order, Product.id)
    )
    return list(result.all())


async def get_inventory_summary(session: AsyncSession, product_id: int) -> dict[str, int]:
    result = await session.scalars(
        select(InventoryItem).where(InventoryItem.product_id == product_id).order_by(InventoryItem.id)
    )
    items = list(result.all())
    counter = Counter(item.status.value for item in items)
    return {
        "total_count": len(items),
        "available_count": counter.get(InventoryStatus.AVAILABLE.value, 0),
        "sold_count": counter.get(InventoryStatus.SOLD.value, 0),
        "reserved_count": counter.get(InventoryStatus.RESERVED.value, 0),
        "deleted_count": counter.get(InventoryStatus.DELETED.value, 0),
    }


async def list_inventory_items(
    session: AsyncSession,
    *,
    product_id: int,
    status: InventoryStatus | None = None,
    limit: int = 30,
) -> list[InventoryItem]:
    stmt = select(InventoryItem).where(InventoryItem.product_id == product_id)
    if status is not None:
        stmt = stmt.where(InventoryItem.status == status)
    stmt = stmt.order_by(desc(InventoryItem.created_at), desc(InventoryItem.id)).limit(limit)
    result = await session.scalars(stmt)
    return list(result.all())


async def add_inventory_item(
    session: AsyncSession,
    *,
    product_id: int,
    title: str,
    content: str,
    instruction: str,
) -> InventoryItem:
    item = InventoryItem(
        product_id=product_id,
        title=title.strip(),
        content=content.strip(),
        instruction=instruction.strip(),
        status=InventoryStatus.AVAILABLE,
    )
    session.add(item)
    await session.flush()
    return item


async def soft_delete_inventory_item(session: AsyncSession, item: InventoryItem) -> InventoryItem:
    item.status = InventoryStatus.DELETED
    item.deleted_at = utcnow()
    await session.flush()
    return item


async def count_available_inventory(session: AsyncSession, product_id: int) -> int:
    result = await session.scalars(
        select(InventoryItem.id).where(
            InventoryItem.product_id == product_id,
            InventoryItem.status == InventoryStatus.AVAILABLE,
        )
    )
    return len(result.all())


async def claim_available_inventory_item(session: AsyncSession, product_id: int) -> InventoryItem | None:
    result = await session.scalars(
        select(InventoryItem)
        .where(
            InventoryItem.product_id == product_id,
            InventoryItem.status == InventoryStatus.AVAILABLE,
        )
        .order_by(InventoryItem.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    return result.first()


async def sell_inventory_item(
    session: AsyncSession,
    *,
    item: InventoryItem,
    user_id: int,
    order_id: int,
) -> InventoryItem | None:
    if item is None:
        return None
    item.status = InventoryStatus.SOLD
    item.sold_to_user_id = user_id
    item.sold_order_id = order_id
    item.sold_at = utcnow()
    await session.flush()
    return item
