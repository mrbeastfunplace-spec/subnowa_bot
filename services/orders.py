from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import OrderStatus, utcnow
from db.models import Order, OrderStatusHistory, PaymentMethod, Product, User
from services.catalog import product_name
from utils.formatting import order_duration_days
from utils.order_numbers import generate_order_number


async def _build_unique_order_number(session: AsyncSession) -> str:
    while True:
        order_number = generate_order_number()
        exists = await session.scalar(select(Order).where(Order.order_number == order_number))
        if exists is None:
            return order_number


async def create_order(
    session: AsyncSession,
    user: User,
    product: Product,
    language: str,
    details: dict | None = None,
    customer_note: str | None = None,
    status: OrderStatus = OrderStatus.PENDING_PAYMENT,
) -> Order:
    order = Order(
        order_number=await _build_unique_order_number(session),
        user_id=user.id,
        product_id=product.id,
        product_code_snapshot=product.code,
        product_name_snapshot=product_name(product, language),
        amount=product.price,
        currency=product.currency,
        status=status,
        workflow_type=product.workflow_type,
        delivery_type=product.delivery_type,
        language=language,
        customer_note=customer_note,
        details=details or {},
    )
    session.add(order)
    await session.flush()
    await add_history(session, order, None, status, changed_by_telegram_id=user.telegram_id)
    return order


async def create_custom_request(
    session: AsyncSession,
    user: User,
    language: str,
    note: str,
) -> Order:
    order = Order(
        order_number=await _build_unique_order_number(session),
        user_id=user.id,
        product_id=None,
        product_code_snapshot="custom_request",
        product_name_snapshot="Custom request",
        amount=0,
        currency="UZS",
        status=OrderStatus.PROCESSING,
        workflow_type="custom_request",
        delivery_type="manual",
        language=language,
        customer_note=note,
        details={"note": note},
    )
    session.add(order)
    await session.flush()
    await add_history(session, order, None, OrderStatus.PROCESSING, changed_by_telegram_id=user.telegram_id)
    return order


async def add_history(
    session: AsyncSession,
    order: Order,
    from_status: OrderStatus | None,
    to_status: OrderStatus,
    changed_by_telegram_id: int | None = None,
    note: str | None = None,
) -> None:
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=to_status,
        changed_by_telegram_id=changed_by_telegram_id,
        note=note,
    )
    session.add(history)


async def change_status(
    session: AsyncSession,
    order: Order,
    new_status: OrderStatus,
    changed_by_telegram_id: int | None = None,
    note: str | None = None,
) -> Order:
    old_status = order.status
    order.status = new_status
    if new_status == OrderStatus.COMPLETED:
        completed_at = utcnow()
        order.completed_at = completed_at
        duration_days = order_duration_days(order.product_code_snapshot)
        order.expires_at = completed_at + timedelta(days=duration_days) if duration_days is not None else None
    order.updated_at = utcnow()
    await add_history(session, order, old_status, new_status, changed_by_telegram_id, note)
    await session.flush()
    return order


async def attach_payment_method(session: AsyncSession, order: Order, payment_method: PaymentMethod) -> Order:
    order.payment_method_id = payment_method.id
    await session.flush()
    return order


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


async def update_payment_meta(
    session: AsyncSession,
    order: Order,
    *,
    payment_provider: str | None = None,
    payment_status: str | None = None,
    invoice_id: str | None = None,
    invoice_uuid: str | None = None,
    checkout_url: str | None = None,
    invoice_expiry_at: datetime | None = None,
) -> Order:
    if payment_provider is not None:
        order.payment_provider = payment_provider
    if payment_status is not None:
        order.payment_status = payment_status
    if invoice_id is not None:
        order.invoice_id = invoice_id
    if invoice_uuid is not None:
        order.invoice_uuid = invoice_uuid
    if checkout_url is not None:
        order.checkout_url = checkout_url
    if invoice_expiry_at is not None or order.invoice_expiry_at is not None:
        order.invoice_expiry_at = _normalize_datetime(invoice_expiry_at)
    order.updated_at = utcnow()
    await session.flush()
    return order


async def store_checkout_message_ref(
    session: AsyncSession,
    order: Order,
    *,
    chat_id: int,
    message_id: int,
) -> Order:
    details = dict(order.details or {})
    details["checkout_message_chat_id"] = int(chat_id)
    details["checkout_message_id"] = int(message_id)
    order.details = details
    order.updated_at = utcnow()
    await session.flush()
    return order


async def save_payment_proof(
    session: AsyncSession,
    order: Order,
    file_id: str,
    file_type: str,
    changed_by_telegram_id: int | None = None,
) -> Order:
    order.payment_proof_file_id = file_id
    order.payment_proof_type = file_type
    return await change_status(
        session,
        order,
        OrderStatus.WAITING_CHECK,
        changed_by_telegram_id=changed_by_telegram_id,
    )


async def get_order_by_id(session: AsyncSession, order_id: int) -> Order | None:
    return await session.scalar(select(Order).where(Order.id == order_id))


async def get_order_by_number(session: AsyncSession, order_number: str) -> Order | None:
    return await session.scalar(select(Order).where(Order.order_number == order_number))


async def get_order_by_invoice_reference(session: AsyncSession, reference: str) -> Order | None:
    cleaned = (reference or "").strip()
    if not cleaned:
        return None
    return await session.scalar(
        select(Order).where(
            or_(
                Order.invoice_id == cleaned,
                Order.invoice_uuid == cleaned,
            )
        )
    )


async def get_order_by_reference(session: AsyncSession, reference: str) -> Order | None:
    cleaned = (reference or "").strip()
    if not cleaned:
        return None

    normalized = cleaned[1:].strip() if cleaned.startswith("#") else cleaned
    if normalized.isdigit():
        return await get_order_by_id(session, int(normalized))

    return await get_order_by_number(session, cleaned)


async def list_orders(
    session: AsyncSession,
    statuses: list[str] | None = None,
    limit: int = 20,
) -> list[Order]:
    stmt = select(Order).order_by(desc(Order.created_at))
    if statuses:
        stmt = stmt.where(Order.status.in_([OrderStatus(status) for status in statuses]))
    stmt = stmt.limit(limit)
    result = await session.scalars(stmt)
    return list(result.all())
