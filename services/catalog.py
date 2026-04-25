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


def service_name(product: Product, language: str) -> str:
    return (product.service_name or "").strip() or product_name(product, language)


def product_description(product: Product, language: str) -> str:
    return pick_translation(product.translations, language, "description")


def is_ready_access_product(product: Product) -> bool:
    return (product.product_type or "").strip() == "ready_access" or (product.delivery_type or "").strip() == "auto"


def product_type_label(product_or_type: Product | str, language: str) -> str:
    product_type = product_or_type if isinstance(product_or_type, str) else (product_or_type.product_type or "")
    translations = {
        "personal_account": {
            "ru": "Личный аккаунт",
            "uz": "Shaxsiy akkaunt",
            "en": "Personal account",
        },
        "ready_access": {
            "ru": "Готовый доступ",
            "uz": "Tayyor kirish",
            "en": "Ready access",
        },
    }
    labels = translations.get(product_type, {})
    return labels.get(language) or labels.get("ru") or product_type or "-"


def product_type_icon(product_or_type: Product | str) -> str:
    product_type = product_or_type if isinstance(product_or_type, str) else (product_or_type.product_type or "")
    if product_type == "ready_access":
        return "📦"
    if product_type == "personal_account":
        return "👤"
    return "💎"


def product_price_line(product: Product) -> str:
    if Decimal(product.price or 0) <= 0:
        return "0"
    return format_money(product.price, product.currency)


def render_product_text(product: Product, language: str) -> str:
    price_label = "Цена" if language == "ru" else ("Narx" if language == "uz" else "Price")
    delivery_label = "Выдача" if language == "ru" else ("Yetkazish" if language == "uz" else "Delivery")
    lines = [f"<b>{service_name(product, language)}</b>"]
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


async def list_service_variants(session: AsyncSession, product: Product) -> list[Product]:
    if not (product.service_name or "").strip():
        return [product]
    result = await session.scalars(
        select(Product)
        .where(
            Product.service_name == product.service_name,
            Product.status == ProductStatus.ACTIVE,
        )
        .order_by(Product.sort_order, Product.id)
    )
    variants = list(result.all())
    return variants or [product]
