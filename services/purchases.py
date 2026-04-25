from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from db.base import BalanceTransactionType, CheckoutSessionStatus, OrderStatus, utcnow
from db.models import CheckoutSession, Order, Product, User
from services.balance import credit_balance, debit_balance
from services.catalog import is_ready_access_product
from services.checkout import complete_checkout_session, get_checkout_session
from services.inventory import (
    claim_available_inventory_item,
    count_available_inventory,
    inventory_delivery_text,
    sell_inventory_item,
)
from services.orders import change_status, create_order, get_order_by_id
from services.users import get_user_by_id


@dataclass(slots=True)
class PurchaseExecutionResult:
    ok: bool
    reason: str
    checkout: CheckoutSession | None = None
    order: Order | None = None
    user: User | None = None
    product: Product | None = None
    delivery_content: str | None = None


async def preview_checkout_stock(session: AsyncSession, product: Product) -> bool:
    if not is_ready_access_product(product):
        return True
    return await count_available_inventory(session, product.id) > 0


async def execute_checkout(
    session: AsyncSession,
    *,
    checkout_id: int,
    language: str,
) -> PurchaseExecutionResult:
    checkout = await get_checkout_session(session, checkout_id)
    if checkout is None:
        return PurchaseExecutionResult(ok=False, reason="missing")
    if checkout.status == CheckoutSessionStatus.COMPLETED:
        order = await get_order_by_id(session, checkout.order_id) if checkout.order_id else None
        return PurchaseExecutionResult(ok=False, reason="processed", checkout=checkout, order=order)
    if checkout.status != CheckoutSessionStatus.PROCESSING:
        return PurchaseExecutionResult(ok=False, reason=checkout.status.value, checkout=checkout)

    user = await get_user_by_id(session, checkout.user_id)
    product = checkout.product
    if user is None or product is None:
        return PurchaseExecutionResult(ok=False, reason="missing_dependencies", checkout=checkout)

    inventory_item = None
    if is_ready_access_product(product):
        inventory_item = await claim_available_inventory_item(session, product.id)
        if inventory_item is None:
            checkout.status = CheckoutSessionStatus.CANCELLED
            checkout.processed_at = utcnow()
            await session.flush()
            return PurchaseExecutionResult(ok=False, reason="stock_empty", checkout=checkout, user=user, product=product)

    purchase_tx = await debit_balance(
        session,
        user_id=user.id,
        amount=checkout.amount,
        tx_type=BalanceTransactionType.PURCHASE,
        source="checkout",
        source_id=checkout.id,
    )
    if purchase_tx is None:
        checkout.status = CheckoutSessionStatus.CANCELLED
        checkout.processed_at = utcnow()
        await session.flush()
        return PurchaseExecutionResult(ok=False, reason="insufficient_balance", checkout=checkout, user=user, product=product)
    user.balance = purchase_tx.balance_after

    order = await create_order(
        session,
        user=user,
        product=product,
        language=language,
        details=dict(checkout.payload or {}),
        status=OrderStatus.PAID if is_ready_access_product(product) else OrderStatus.PROCESSING,
        paid_at=utcnow(),
    )

    if is_ready_access_product(product):
        sold_item = await sell_inventory_item(
            session,
            item=inventory_item,
            user_id=user.id,
            order_id=order.id,
        )
        delivery_content = inventory_delivery_text(sold_item) if sold_item else ""
        order.delivery_content = delivery_content
        details = dict(order.details or {})
        details["delivery_content"] = delivery_content
        order.details = details
        await change_status(
            session,
            order,
            OrderStatus.COMPLETED,
            changed_by_telegram_id=user.telegram_id,
            note="auto delivered from inventory",
        )
        await complete_checkout_session(session, checkout, order_id=order.id)
        return PurchaseExecutionResult(
            ok=True,
            reason="completed",
            checkout=checkout,
            order=order,
            user=user,
            product=product,
            delivery_content=delivery_content,
        )

    await complete_checkout_session(session, checkout, order_id=order.id)
    return PurchaseExecutionResult(
        ok=True,
        reason="processing",
        checkout=checkout,
        order=order,
        user=user,
        product=product,
    )


async def refund_order(
    session: AsyncSession,
    *,
    order: Order,
    admin_id: int,
) -> PurchaseExecutionResult:
    user = order.user or await get_user_by_id(session, order.user_id)
    if user is None:
        return PurchaseExecutionResult(ok=False, reason="missing_user", order=order)
    if order.status == OrderStatus.REFUNDED:
        return PurchaseExecutionResult(ok=False, reason="already_refunded", order=order, user=user)
    await credit_balance(
        session,
        user_id=user.id,
        amount=order.amount,
        tx_type=BalanceTransactionType.REFUND,
        source="order",
        source_id=order.id,
    )
    await session.refresh(user)
    await change_status(
        session,
        order,
        OrderStatus.REFUNDED,
        changed_by_telegram_id=admin_id,
        note="refunded by admin",
        admin_id=admin_id,
    )
    return PurchaseExecutionResult(ok=True, reason="refunded", order=order, user=user, product=order.product)
