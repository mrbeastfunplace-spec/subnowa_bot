from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Language(str, Enum):
    RU = "ru"
    UZ = "uz"
    EN = "en"


class ProductStatus(str, Enum):
    ACTIVE = "active"
    HIDDEN = "hidden"


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    WAITING_CHECK = "waiting_check"
    PAID = "paid"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PaymentProviderType(str, Enum):
    CLICK = "click"
    CARD = "card"
    CRYPTO = "crypto"
    OTHER = "other"


class ButtonActionType(str, Enum):
    CALLBACK = "callback"
    URL = "url"

