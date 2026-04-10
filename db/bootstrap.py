from __future__ import annotations

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
    for item in DEFAULT_CATEGORIES:
        category = await session.scalar(select(Category).where(Category.code == item["code"]))
        if category is None:
            category = Category(code=item["code"])
            session.add(category)
            await session.flush()

        category.slug = item["slug"]
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


async def seed_products(session: AsyncSession) -> None:
    categories = {row.code: row for row in (await session.scalars(select(Category))).all()}
    for item in DEFAULT_PRODUCTS:
        product = await session.scalar(select(Product).where(Product.code == item["code"]))
        if product is None:
            product = Product(code=item["code"])
            session.add(product)
            await session.flush()

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
            await session.flush()

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
            await session.flush()

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
            await session.flush()

        layout.title = item["title"]
        layout.scope = item["scope"]
        layout.is_active = True

        existing_buttons = {button.code: button for button in layout.buttons}
        for button_data in item["buttons"]:
            button = existing_buttons.get(button_data["code"])
            if button is None:
                button = LayoutButton(layout=layout, code=button_data["code"])
                session.add(button)
                await session.flush()

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
