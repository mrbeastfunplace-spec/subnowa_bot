from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import ProductStatus
from db.models import Category, Product
from utils.formatting import format_money
from utils.translations import pick_translation


def category_name(category: Category, language: str) -> str:
    return pick_translation(category.translations, language, "name") or category.code


def product_name(product: Product, language: str) -> str:
    return pick_translation(product.translations, language, "name") or product.code


def product_description(product: Product, language: str) -> str:
    return pick_translation(product.translations, language, "description")


def product_price_line(product: Product) -> str:
    if Decimal(product.price or 0) <= 0:
        return "0"
    return format_money(product.price, product.currency)


def render_product_text(product: Product, language: str) -> str:
    price_label = "Цена" if language == "ru" else ("Narx" if language == "uz" else "Price")
    delivery_label = "Выдача" if language == "ru" else ("Yetkazish" if language == "uz" else "Delivery")
    lines = [f"<b>{product_name(product, language)}</b>"]
    description = product_description(product, language)
    if description:
        lines.append("")
        lines.append(description)
    lines.append("")
    lines.append(f"{price_label}: <b>{format_money(product.price, product.currency)}</b>")
    lines.append(f"{delivery_label}: <b>{product.delivery_type}</b>")
    return "\n".join(lines)


async def list_categories(session: AsyncSession) -> list[Category]:
    result = await session.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.id)
    )
    return list(result.all())


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.scalar(select(Category).where(Category.id == category_id))


async def list_category_products(session: AsyncSession, category_id: int) -> list[Product]:
    result = await session.scalars(
        select(Product)
        .where(
            Product.category_id == category_id,
            Product.status == ProductStatus.ACTIVE,
            Product.show_in_catalog.is_(True),
        )
        .order_by(Product.sort_order, Product.id)
    )
    return list(result.all())


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.scalar(select(Product).where(Product.id == product_id))


async def get_product_by_code(session: AsyncSession, code: str) -> Product | None:
    return await session.scalar(select(Product).where(Product.code == code))
