from __future__ import annotations

from decimal import Decimal, InvalidOperation

from db.base import OrderStatus


STATUS_LABELS = {
    "ru": {
        OrderStatus.PENDING_PAYMENT.value: "Ожидает оплаты",
        OrderStatus.WAITING_CHECK.value: "На проверке",
        OrderStatus.PAID.value: "Оплачен",
        OrderStatus.PROCESSING.value: "В работе",
        OrderStatus.COMPLETED.value: "Завершён",
        OrderStatus.REJECTED.value: "Отклонён",
        OrderStatus.CANCELLED.value: "Отменён",
    },
    "uz": {
        OrderStatus.PENDING_PAYMENT.value: "To'lov kutilmoqda",
        OrderStatus.WAITING_CHECK.value: "Tekshiruvda",
        OrderStatus.PAID.value: "To'langan",
        OrderStatus.PROCESSING.value: "Jarayonda",
        OrderStatus.COMPLETED.value: "Yakunlangan",
        OrderStatus.REJECTED.value: "Rad etilgan",
        OrderStatus.CANCELLED.value: "Bekor qilingan",
    },
    "en": {
        OrderStatus.PENDING_PAYMENT.value: "Pending payment",
        OrderStatus.WAITING_CHECK.value: "Waiting check",
        OrderStatus.PAID.value: "Paid",
        OrderStatus.PROCESSING.value: "Processing",
        OrderStatus.COMPLETED.value: "Completed",
        OrderStatus.REJECTED.value: "Rejected",
        OrderStatus.CANCELLED.value: "Cancelled",
    },
}


def format_money(value: Decimal | str | int | float, currency: str) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    normalized = f"{amount:,.2f}".replace(",", " ")
    if normalized.endswith(".00"):
        normalized = normalized[:-3]
    return f"{normalized} {currency}".strip()


def order_status_label(status: str, language: str) -> str:
    return STATUS_LABELS.get(language, STATUS_LABELS["ru"]).get(status, status)
