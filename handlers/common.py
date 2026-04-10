from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import Category, Order, PaymentMethod, Product
from services.catalog import category_name, product_name
from services.payments import payment_title
from utils.formatting import order_status_label


def language_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
                InlineKeyboardButton(text="🇺🇸 English", callback_data="lang:en"),
            ]
        ]
    )


def simple_back_markup(callback_data: str = "menu:main", text: str = "Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback_data)]]
    )


def categories_markup(categories: list[Category], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=category_name(category, language), callback_data=f"catalog:cat:{category.id}")]
        for category in categories
    ]
    custom_text = "Другая заявка" if language == "ru" else ("Boshqa so'rov" if language == "uz" else "Custom request")
    rows.append([InlineKeyboardButton(text=custom_text, callback_data="custom:open")])
    rows.append([InlineKeyboardButton(text="Меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_markup(products: list[Product], language: str, category_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=product_name(product, language), callback_data=f"product:view:{product.id}")]
        for product in products
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"catalog:back:{category_id}")])
    rows.append([InlineKeyboardButton(text="Меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_markup(product: Product, language: str, include_trial: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Купить" if language == "ru" else ("Sotib olish" if language == "uz" else "Buy"), callback_data=f"product:buy:{product.id}")]]
    if include_trial:
        rows.append([InlineKeyboardButton(text="Trial 3 дня" if language == "ru" else ("Trial 3 kun" if language == "uz" else "Trial 3 days"), callback_data="product:trial")])
    if product.category_id:
        rows.append([InlineKeyboardButton(text="Назад" if language == "ru" else ("Ortga" if language == "uz" else "Back"), callback_data=f"catalog:cat:{product.category_id}")])
    rows.append([InlineKeyboardButton(text="Меню" if language == "ru" else ("Menyu" if language == "uz" else "Menu"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gmail_choice_markup(product_id: int, language: str) -> InlineKeyboardMarkup:
    use_saved = "Использовать этот Gmail" if language == "ru" else ("Shu Gmailni ishlatish" if language == "uz" else "Use this Gmail")
    use_other = "Указать другой Gmail" if language == "ru" else ("Boshqa Gmail kiritish" if language == "uz" else "Use another Gmail")
    back = "Назад" if language == "ru" else ("Ortga" if language == "uz" else "Back")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=use_saved, callback_data=f"chatgpt:saved:{product_id}")],
            [InlineKeyboardButton(text=use_other, callback_data=f"chatgpt:other:{product_id}")],
            [InlineKeyboardButton(text=back, callback_data=f"product:view:{product_id}")],
        ]
    )


def subscription_check_markup(product_id: int, language: str) -> InlineKeyboardMarkup:
    subscribe = "Подписаться" if language == "ru" else ("Obuna bo'lish" if language == "uz" else "Subscribe")
    check = "Проверить подписку" if language == "ru" else ("Obunani tekshirish" if language == "uz" else "Check subscription")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subscribe, url="https://t.me/")],
            [InlineKeyboardButton(text=check, callback_data=f"trial:check:{product_id}")],
            [InlineKeyboardButton(text="Меню" if language == "ru" else ("Menyu" if language == "uz" else "Menu"), callback_data="menu:main")],
        ]
    )


def payment_methods_markup(order_id: int, methods: list[PaymentMethod], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=payment_title(method, language), callback_data=f"order:pay:{order_id}:{method.id}")]
        for method in methods
    ]
    rows.append([InlineKeyboardButton(text="Отмена" if language == "ru" else ("Bekor qilish" if language == "uz" else "Cancel"), callback_data=f"order:cancel:{order_id}")])
    rows.append([InlineKeyboardButton(text="Меню" if language == "ru" else ("Menyu" if language == "uz" else "Menu"), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_detail_markup(order: Order, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=order_status_label(order.status.value, language), callback_data="noop")],
            [InlineKeyboardButton(text="Меню" if language == "ru" else ("Menyu" if language == "uz" else "Menu"), callback_data="menu:main")],
        ]
    )


def completed_orders_markup(orders: list[Order], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{order.product_name_snapshot} • {order.order_number}", callback_data=f"order:detail:{order.id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text="Назад" if language == "ru" else ("Ortga" if language == "uz" else "Back"), callback_data="menu:profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
