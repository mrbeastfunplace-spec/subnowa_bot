from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

TASHKENT_TZ = timezone(timedelta(hours=5))

ORDER_DURATION_DAYS = {
    "chatgpt_plus_month": 30,
    "capcut_pro_month": 30,
    "chatgpt_trial_3d": 3,
}

ORDER_DURATION_LABELS = {
    "ru": {
        "chatgpt_plus_month": "25-30 дней",
        "capcut_pro_month": "30 дней",
        "chatgpt_trial_3d": "3 дня",
    },
    "uz": {
        "chatgpt_plus_month": "25-30 kun",
        "capcut_pro_month": "30 kun",
        "chatgpt_trial_3d": "3 kun",
    },
    "en": {
        "chatgpt_plus_month": "25-30 days",
        "capcut_pro_month": "30 days",
        "chatgpt_trial_3d": "3 days",
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


def order_duration_days(product_code: str | None) -> int | None:
    return ORDER_DURATION_DAYS.get((product_code or "").strip())


def order_duration_label(product_code: str | None, language: str) -> str:
    return ORDER_DURATION_LABELS.get(language, ORDER_DURATION_LABELS["ru"]).get((product_code or "").strip(), "-")


def format_datetime_local(value: datetime | None) -> str:
    if value is None:
        return "-"
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return normalized.astimezone(TASHKENT_TZ).strftime("%d.%m.%Y %H:%M")


def resolve_order_expiration(order: object | None) -> datetime | None:
    if order is None:
        return None
    explicit_expiration = getattr(order, "expires_at", None)
    if explicit_expiration is not None:
        return explicit_expiration
    duration_days = order_duration_days(getattr(order, "product_code_snapshot", None))
    if duration_days is None:
        return None
    anchor = getattr(order, "completed_at", None)
    if anchor is None:
        return None
    return anchor + timedelta(days=duration_days)


def order_display_number(order_or_id: object | int | None) -> str:
    if isinstance(order_or_id, int):
        return f"#{order_or_id}"
    order_id = getattr(order_or_id, "id", None)
    if isinstance(order_id, int):
        return f"#{order_id}"
    return "-"


def user_display_name(user: object | None, fallback_id: int | None = None) -> str:
    username = (getattr(user, "username", None) or "").strip()
    if username:
        return f"@{username.lstrip('@')}"

    full_name = (getattr(user, "full_name", None) or "").strip()
    if full_name:
        return full_name

    telegram_id = getattr(user, "telegram_id", None)
    if isinstance(telegram_id, int):
        return str(telegram_id)
    if isinstance(fallback_id, int):
        return str(fallback_id)
    return "-"
