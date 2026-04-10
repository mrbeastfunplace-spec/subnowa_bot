from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from config import Settings
from db.base import ButtonActionType, Language, PaymentProviderType, ProductStatus
from db.defaults import DEFAULT_CATEGORIES, DEFAULT_LAYOUTS, DEFAULT_PRODUCTS, DEFAULT_TEXTS, get_default_payment_methods, get_default_settings
from db.models import (
    Base,
    Category,
    CategoryTranslation,
    Layout,
    LayoutButton,
    LayoutButtonTranslation,
    PaymentMethod,
    PaymentMethodTranslation,
    Product,
    ProductPaymentMethod,
    ProductTranslation,
    Setting,
    TextEntry,
    TextTranslation,
)


_CATEGORY_SLUG_MAX_LENGTH = 64


def _slugify(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = ascii_value.strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]+", "", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")


def _fit_slug(value: str) -> str:
    return value[:_CATEGORY_SLUG_MAX_LENGTH].strip("-")


def _slug_with_suffix(base: str, suffix: str | None = None) -> str:
    fitted_base = _fit_slug(base) or "category"
    if not suffix:
        return fitted_base

    fitted_suffix = _slugify(suffix)
    if not fitted_suffix:
        return fitted_base

    max_base_length = _CATEGORY_SLUG_MAX_LENGTH - len(fitted_suffix) - 1
    trimmed_base = _fit_slug(fitted_base[:max_base_length]) or "category"
    return f"{trimmed_base}-{fitted_suffix}"


def _category_slug_sources(category: Category | None, item: dict | None = None) -> list[str]:
    sources: list[str] = []
    if item is not None:
        explicit_slug = item.get("slug")
        if isinstance(explicit_slug, str):
            sources.append(explicit_slug)

        code = item.get("code")
        if isinstance(code, str):
            sources.append(code)

        translations = item.get("translations")
        if isinstance(translations, dict):
            for lang_code in (Language.EN.value, Language.UZ.value, Language.RU.value):
                payload = translations.get(lang_code)
                if isinstance(payload, dict):
                    name = payload.get("name")
                    if isinstance(name, str):
                        sources.append(name)

    if category is not None:
        if category.slug:
            sources.append(category.slug)
        sources.append(category.code)
        for translation in category.translations:
            if translation.name:
                sources.append(translation.name)

    return sources


def _claim_category_slug(
    category: Category,
    used_slugs: dict[str, Category],
    sources: list[str],
    *,
    preserve_current: bool,
) -> str:
    current_slug = _slugify(category.slug)
    if current_slug and used_slugs.get(current_slug) is category:
        used_slugs.pop(current_slug, None)

    ordered_sources: list[str] = []
    if preserve_current and current_slug:
        ordered_sources.append(current_slug)
    ordered_sources.extend(source for source in sources if source)

    base_slug = ""
    for source in ordered_sources:
        candidate = _slugify(source)
        if candidate:
            base_slug = candidate
            break

    if not base_slug:
        base_slug = _slugify(category.code) or "category"

    candidate = _fit_slug(base_slug) or "category"
    owner = used_slugs.get(candidate)
    if owner in (None, category):
        used_slugs[candidate] = category
        return candidate

    code_slug = _slugify(category.code)
    if code_slug:
        candidate = _slug_with_suffix(base_slug, code_slug)
        owner = used_slugs.get(candidate)
        if owner in (None, category):
            used_slugs[candidate] = category
            return candidate

    counter = 2
    while True:
        candidate = _slug_with_suffix(base_slug, str(counter))
        owner = used_slugs.get(candidate)
        if owner in (None, category):
            used_slugs[candidate] = category
            return candidate
        counter += 1


async def initialize_database(
    engine: AsyncEngine,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await seed_settings(session, settings)
        await seed_categories(session)
        await normalize_category_slugs(session)
        await seed_products(session)
        await seed_payment_methods(session)
        await seed_texts(session)
        await seed_layouts(session, settings)
        await seed_product_payment_links(session)
        await session.commit()


async def seed_settings(session: AsyncSession, settings: Settings) -> None:
    for item in get_default_settings(settings):
        row = await session.scalar(select(Setting).where(Setting.key == item["key"]))
        if row is None:
            row = Setting(key=item["key"])
            session.add(row)
        row.value = item["value"]
        row.value_type = item["value_type"]
        row.description = item["description"]


async def seed_categories(session: AsyncSession) -> None:
    categories = (await session.scalars(select(Category))).all()
    categories_by_code = {row.code: row for row in categories}
    used_slugs = {
        normalized_slug: row
        for row in categories
        if (normalized_slug := _slugify(row.slug))
    }

    for item in DEFAULT_CATEGORIES:
        category = categories_by_code.get(item["code"])
        if category is None:
            category = Category(code=item["code"])
            session.add(category)
            categories_by_code[category.code] = category

        category.slug = _claim_category_slug(
            category,
            used_slugs,
            _category_slug_sources(category, item),
            preserve_current=False,
        )
        category.sort_order = item["sort_order"]
        category.is_active = item["is_active"]

        existing = {tr.language.value: tr for tr in category.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = CategoryTranslation(category=category, language=Language(lang_code))
                session.add(translation)
            translation.name = payload["name"]
            translation.description = payload["description"]


async def normalize_category_slugs(session: AsyncSession) -> None:
    categories = (await session.scalars(select(Category))).all()
    used_slugs: dict[str, Category] = {}

    for category in sorted(categories, key=lambda row: (row.id or 0, row.code)):
        category.slug = _claim_category_slug(
            category,
            used_slugs,
            _category_slug_sources(category),
            preserve_current=True,
        )


async def seed_products(session: AsyncSession) -> None:
    categories = {row.code: row for row in (await session.scalars(select(Category))).all()}
    for item in DEFAULT_PRODUCTS:
        product = await session.scalar(select(Product).where(Product.code == item["code"]))
        if product is None:
            product = Product(code=item["code"])
            session.add(product)

        product.category = categories.get(item["category_code"])
        product.status = ProductStatus(item["status"])
        product.delivery_type = item["delivery_type"]
        product.workflow_type = item["workflow_type"]
        product.price = Decimal(item["price"])
        product.currency = item["currency"]
        product.sort_order = item["sort_order"]
        product.show_in_catalog = item["show_in_catalog"]
        product.extra_data = item["extra_data"]

        existing = {tr.language.value: tr for tr in product.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = ProductTranslation(product=product, language=Language(lang_code))
                session.add(translation)
            translation.name = payload["name"]
            translation.description = payload["description"]


async def seed_payment_methods(session: AsyncSession) -> None:
    for item in get_default_payment_methods():
        payment = await session.scalar(select(PaymentMethod).where(PaymentMethod.code == item["code"]))
        if payment is None:
            payment = PaymentMethod(code=item["code"])
            session.add(payment)

        payment.provider_type = PaymentProviderType(item["provider_type"])
        payment.admin_title = item["admin_title"]
        payment.credentials = item["credentials"]
        payment.sort_order = item["sort_order"]
        payment.is_active = True

        existing = {tr.language.value: tr for tr in payment.translations}
        for lang_code, payload in item["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = PaymentMethodTranslation(payment_method=payment, language=Language(lang_code))
                session.add(translation)
            translation.title = payload["title"]
            translation.instructions = payload["instructions"]


async def seed_texts(session: AsyncSession) -> None:
    for code, payload in DEFAULT_TEXTS.items():
        entry = await session.scalar(select(TextEntry).where(TextEntry.code == code))
        if entry is None:
            entry = TextEntry(code=code)
            session.add(entry)

        entry.group_name = payload["group"]
        entry.description = payload["description"]

        existing = {tr.language.value: tr for tr in entry.translations}
        for lang_code, value in payload["translations"].items():
            translation = existing.get(lang_code)
            if translation is None:
                translation = TextTranslation(text_entry=entry, language=Language(lang_code))
                session.add(translation)
            translation.value = value


async def seed_layouts(session: AsyncSession, settings: Settings) -> None:
    replacement_map = {
        "__SUPPORT_URL__": settings.support_url,
        "__ABOUT_URL__": settings.about_url,
        "__REVIEW_URL__": settings.review_url,
    }

    for item in DEFAULT_LAYOUTS:
        layout = await session.scalar(select(Layout).where(Layout.code == item["code"]))
        if layout is None:
            layout = Layout(code=item["code"])
            session.add(layout)

        layout.title = item["title"]
        layout.scope = item["scope"]
        layout.is_active = True

        existing_buttons = {button.code: button for button in layout.buttons}
        for button_data in item["buttons"]:
            button = existing_buttons.get(button_data["code"])
            if button is None:
                button = LayoutButton(layout=layout, code=button_data["code"])
                session.add(button)

            button.action_type = ButtonActionType(button_data["action_type"])
            button.action_value = replacement_map.get(button_data["action_value"], button_data["action_value"])
            button.style = button_data["style"]
            button.row_index = button_data["row_index"]
            button.sort_order = button_data["sort_order"]
            button.is_active = True

            existing_translations = {tr.language.value: tr for tr in button.translations}
            for lang_code, text in button_data["translations"].items():
                translation = existing_translations.get(lang_code)
                if translation is None:
                    translation = LayoutButtonTranslation(button=button, language=Language(lang_code))
                    session.add(translation)
                translation.text = text


async def seed_product_payment_links(session: AsyncSession) -> None:
    products = {row.code: row for row in (await session.scalars(select(Product))).all()}
    payments = {row.code: row for row in (await session.scalars(select(PaymentMethod))).all()}
    existing_links = {
        (row.product_id, row.payment_method_id): row
        for row in (await session.scalars(select(ProductPaymentMethod))).all()
    }

    link_map = {
        "chatgpt_plus_month": ["click", "card", "usdt_trc20"],
        "capcut_pro_month": ["click", "card", "usdt_trc20"],
        "grok_template": ["click", "card", "usdt_trc20"],
        "adobe_template": ["click", "card", "usdt_trc20"],
    }

    for product_code, payment_codes in link_map.items():
        product = products.get(product_code)
        if product is None:
            continue
        for index, payment_code in enumerate(payment_codes, start=1):
            payment = payments.get(payment_code)
            if payment is None:
                continue
            key = (product.id, payment.id)
            link = existing_links.get(key)
            if link is None:
                link = ProductPaymentMethod(product=product, payment_method=payment)
                session.add(link)
            link.sort_order = index * 10
