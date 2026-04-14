from __future__ import annotations

from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import Settings
from db.models import Order


SEPARATOR = "➖" * 9


def _labels(language: str) -> dict[str, str]:
    if language == "uz":
        return {
            "order": "Buyurtma",
            "product": "Mahsulot",
            "price": "Narx",
            "valid": "To'lov hisobi 15 daqiqa davomida amal qiladi.",
            "status": "To'lovdan keyin holat avtomatik yangilanadi.",
            "button": "To‘lovga o‘tish",
        }
    if language == "en":
        return {
            "order": "Order",
            "product": "Product",
            "price": "Price",
            "valid": "The payment invoice is valid for 15 minutes.",
            "status": "Status will update automatically after payment.",
            "button": "Proceed to payment",
        }
    return {
        "order": "Заказ",
        "product": "Товар",
        "price": "Цена",
        "valid": "Счёт на оплату актуален 15 минут.",
        "status": "Статус обновится автоматически после оплаты.",
        "button": "Перейти к оплате",
    }


def _normalize_amount(value: Decimal | int | float | str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def format_checkout_uzs(value: Decimal | int | float | str) -> str:
    amount = _normalize_amount(value)
    normalized = f"{amount:,.2f}".replace(",", " ")
    if normalized.endswith(".00"):
        normalized = normalized[:-3]
    return f"{normalized} сум"


def format_checkout_usd(value: Decimal | int | float | str) -> str:
    amount = _normalize_amount(value).quantize(Decimal("0.01"))
    return f"${amount:.2f}"


def build_order_card_text(order: Order, language: str, price_usd: Decimal | int | float | str) -> str:
    labels = _labels(language)
    return "\n".join(
        [
            SEPARATOR,
            f"{labels['order']}: #{order.order_number}",
            f"{labels['product']}: {order.product_name_snapshot}",
            f"{labels['price']}: {format_checkout_uzs(order.amount)} ({format_checkout_usd(price_usd)})",
            SEPARATOR,
            labels["valid"],
            labels["status"],
            SEPARATOR,
        ]
    )


def build_checkout_entry_url(settings: Settings, order_number: str) -> str:
    base_url = settings.checkout_entry_base_url
    if not base_url:
        return ""
    return f"{base_url}/checkout/{quote(order_number, safe='')}"


def build_checkout_link_markup(checkout_url: str, language: str) -> InlineKeyboardMarkup:
    labels = _labels(language)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=labels["button"], url=checkout_url, style="success")]]
    )


def build_checkout_markup(settings: Settings, order_number: str, language: str) -> InlineKeyboardMarkup:
    labels = _labels(language)
    url = build_checkout_entry_url(settings, order_number)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=labels["button"], url=url, style="success")]]
    )
