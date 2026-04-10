from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PaymentMethod, Product, ProductPaymentMethod
from payments.providers import get_provider
from utils.translations import pick_translation


def payment_title(payment_method: PaymentMethod, language: str) -> str:
    return pick_translation(payment_method.translations, language, "title") or payment_method.admin_title


def payment_instruction(payment_method: PaymentMethod, language: str) -> str:
    template = pick_translation(payment_method.translations, language, "instructions")
    provider = get_provider(payment_method.provider_type.value)
    return provider.render_instructions(template=template, credentials=payment_method.credentials)


async def list_product_payment_methods(session: AsyncSession, product: Product) -> list[PaymentMethod]:
    result = await session.scalars(
        select(PaymentMethod)
        .join(ProductPaymentMethod, ProductPaymentMethod.payment_method_id == PaymentMethod.id)
        .where(
            ProductPaymentMethod.product_id == product.id,
            PaymentMethod.is_active.is_(True),
        )
        .order_by(ProductPaymentMethod.sort_order, PaymentMethod.sort_order, PaymentMethod.id)
    )
    return list(result.all())


async def get_payment_method(session: AsyncSession, payment_method_id: int) -> PaymentMethod | None:
    return await session.scalar(select(PaymentMethod).where(PaymentMethod.id == payment_method_id))


async def toggle_product_payment_method(
    session: AsyncSession,
    product_id: int,
    payment_method_id: int,
) -> ProductPaymentMethod | None:
    link = await session.scalar(
        select(ProductPaymentMethod).where(
            ProductPaymentMethod.product_id == product_id,
            ProductPaymentMethod.payment_method_id == payment_method_id,
        )
    )
    if link is None:
        link = ProductPaymentMethod(product_id=product_id, payment_method_id=payment_method_id, sort_order=10)
        session.add(link)
        await session.flush()
        return link
    await session.delete(link)
    await session.flush()
    return None
