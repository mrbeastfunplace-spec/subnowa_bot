from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import Category, Order, PaymentMethod, Product
from services.catalog import category_name, product_name
from services.payments import payment_title
from utils.formatting import order_display_number, order_status_label


def _back_label(language: str) -> str:
    return "◀ Назад" if language == "ru" else ("◀ Orqaga" if language == "uz" else "◀ Back")


def _menu_label(language: str) -> str:
    return "🏠 Меню" if language == "ru" else ("🏠 Menyu" if language == "uz" else "🏠 Menu")


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


def simple_back_markup(callback_data: str = "menu:main", text: str = "◀ Назад") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=callback_data)]])


def categories_markup(categories: list[Category], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=category_name(category, language), callback_data=f"catalog:cat:{category.id}")]
        for category in categories
    ]
    custom_text = "Другое" if language == "ru" else ("Boshqa" if language == "uz" else "Other")
    rows.append([InlineKeyboardButton(text=custom_text, callback_data="custom:open")])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def products_markup(products: list[Product], language: str, category_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=product_name(product, language), callback_data=f"product:view:{product.id}")]
        for product in products
    ]
    rows.append([InlineKeyboardButton(text=_back_label(language), callback_data=f"catalog:back:{category_id}")])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_markup(product: Product, language: str, include_trial: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="Оформить" if language == "ru" else ("Rasmiylashtirish" if language == "uz" else "Proceed"),
                callback_data=f"product:buy:{product.id}",
            )
        ]
    ]
    if include_trial:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Попробовать 3 дня бесплатно" if language == "ru" else ("3 kun bepul sinab ko‘rish" if language == "uz" else "Try 3 days for free"),
                    callback_data="product:trial",
                )
            ]
        )
    if product.category_id:
        rows.append([InlineKeyboardButton(text=_back_label(language), callback_data=f"catalog:cat:{product.category_id}")])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gmail_choice_markup(product_id: int, language: str) -> InlineKeyboardMarkup:
    use_saved = "На этот" if language == "ru" else ("Shu Gmail" if language == "uz" else "Use this")
    use_other = "Другой" if language == "ru" else ("Boshqa" if language == "uz" else "Other")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=use_saved, callback_data=f"chatgpt:saved:{product_id}")],
            [InlineKeyboardButton(text=use_other, callback_data=f"chatgpt:other:{product_id}")],
            [InlineKeyboardButton(text=_back_label(language), callback_data=f"product:view:{product_id}")],
        ]
    )


def subscription_check_markup(product_id: int, language: str) -> InlineKeyboardMarkup:
    subscribe = "Подписаться" if language == "ru" else ("Obuna bo'lish" if language == "uz" else "Subscribe")
    check = "Проверить подписку" if language == "ru" else ("Obunani tekshirish" if language == "uz" else "Check subscription")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=subscribe, url="https://t.me/")],
            [InlineKeyboardButton(text=check, callback_data=f"trial:check:{product_id}")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def payment_methods_markup(order_id: int, methods: list[PaymentMethod], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=payment_title(method, language), callback_data=f"order:pay:{order_id}:{method.id}")]
        for method in methods
    ]
    rows.append([InlineKeyboardButton(text="Отмена" if language == "ru" else ("Bekor qilish" if language == "uz" else "Cancel"), callback_data=f"order:cancel:{order_id}")])
    rows.append([InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_detail_markup(order: Order, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=order_status_label(order.status.value, language), callback_data="noop")],
            [InlineKeyboardButton(text=_menu_label(language), callback_data="menu:main")],
        ]
    )


def completed_orders_markup(orders: list[Order], language: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{order.product_name_snapshot} • {order_display_number(order)}", callback_data=f"order:detail:{order.id}")]
        for order in orders
    ]
    rows.append([InlineKeyboardButton(text=_back_label(language), callback_data="menu:profile")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
