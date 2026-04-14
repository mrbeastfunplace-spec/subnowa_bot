from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from aiogram import Bot
from aiogram.types import LabeledPrice, Message

from config import Settings
from db.base import OrderStatus
from db.models import Order


_DEFAULT_EXPONENT = 2
_CURRENCY_EXPONENTS = {
    "JPY": 0,
    "KRW": 0,
    "VND": 0,
    "XTR": 0,
}

_PRODUCT_COPY = {
    "chatgpt_plus_month": {
        "title": {
            "ru": "ChatGPT Plus",
            "uz": "ChatGPT Plus",
            "en": "ChatGPT Plus",
        },
        "description": {
            "ru": "99 000 сум ($8.17)",
            "uz": "99 000 so'm ($8.17)",
            "en": "99 000 UZS ($8.17)",
        },
    },
    "capcut_pro_month": {
        "title": {
            "ru": "CapCut Pro (1 месяц)",
            "uz": "CapCut Pro (1 oy)",
            "en": "CapCut Pro (1 month)",
        },
        "description": {
            "ru": "Доступ на 30 дней. Готовый аккаунт отправим после оплаты.",
            "uz": "30 kunlik kirish. To‘lovdan keyin tayyor akkaunt yuboriladi.",
            "en": "30-day access. Ready account is sent after payment.",
        },
    },
}


def provider_token_enabled(settings: Settings) -> bool:
    return bool((settings.payment_provider_token or "").strip())


def can_pay_order(order: Order) -> bool:
    return order.status not in {
        OrderStatus.PAID,
        OrderStatus.PROCESSING,
        OrderStatus.COMPLETED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    }


def invoice_payload(order: Order) -> str:
    return order.order_number


def invoice_start_parameter(order: Order) -> str:
    raw = (order.order_number or "order").lower()
    normalized = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-") or "order"
    return f"subnowa-{normalized}"[:64]


def payment_provider_name() -> str:
    return "telegram_payments"


def payment_unavailable_text(language: str) -> str:
    if language == "uz":
        return "To'lov vaqtincha mavjud emas. Iltimos, keyinroq urinib ko'ring."
    if language == "en":
        return "Payment is temporarily unavailable. Please try again later."
    return "Оплата временно недоступна. Пожалуйста, попробуйте позже."


def invalid_order_text(language: str) -> str:
    if language == "uz":
        return "Bu buyurtma uchun to'lovni davom ettirib bo'lmaydi."
    if language == "en":
        return "This order can no longer be paid."
    return "Для этого заказа оплата уже недоступна."


def pre_checkout_error_text(language: str) -> str:
    if language == "uz":
        return "Buyurtmani tekshirib bo'lmadi. Iltimos, qayta urinib ko'ring."
    if language == "en":
        return "We could not validate this order. Please try again."
    return "Не удалось проверить заказ. Пожалуйста, попробуйте ещё раз."


def _currency_exponent(currency: str) -> int:
    normalized = (currency or "").upper()
    return _CURRENCY_EXPONENTS.get(normalized, _DEFAULT_EXPONENT)


def _invoice_currency(order: Order) -> str:
    return (order.currency or "UZS").upper()


def _total_amount(order: Order) -> int:
    exponent = _currency_exponent(order.currency)
    multiplier = Decimal(10) ** exponent
    amount = Decimal(str(order.amount or 0)) * multiplier
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _copy_for_order(order: Order, language: str) -> tuple[str, str]:
    copy = _PRODUCT_COPY.get(order.product_code_snapshot or "")
    if not copy:
        title = order.product_name_snapshot or order.product_code_snapshot or "Order"
        return title, title
    title = copy["title"].get(language) or copy["title"]["ru"]
    description = copy["description"].get(language) or copy["description"]["ru"]
    return title, description


def invoice_prices(order: Order, language: str) -> list[LabeledPrice]:
    title, _ = _copy_for_order(order, language)
    return [LabeledPrice(label=title, amount=_total_amount(order))]


def invoice_total_amount(order: Order) -> int:
    return _total_amount(order)


async def send_order_invoice(
    bot: Bot,
    settings: Settings,
    order: Order,
    *,
    chat_id: int,
    language: str,
) -> Message:
    title, description = _copy_for_order(order, language)
    return await bot.send_invoice(
        chat_id=chat_id,
        title=title,
        description=description,
        payload=invoice_payload(order),
        currency=_invoice_currency(order),
        prices=invoice_prices(order, language),
        provider_token=(settings.payment_provider_token or "").strip(),
        start_parameter=invoice_start_parameter(order),
    )
