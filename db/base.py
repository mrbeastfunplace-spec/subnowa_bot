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
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentProviderType(str, Enum):
    CLICK = "click"
    CARD = "card"
    CRYPTO = "crypto"
    OTHER = "other"


class ButtonActionType(str, Enum):
    CALLBACK = "callback"
    URL = "url"


class ChatGPTWorkspaceStatus(str, Enum):
    PENDING_SETUP = "pending_setup"
    ACTIVE = "active"
    INVALID_AUTH = "invalid_auth"
    DISABLED = "disabled"


class BroadcastKind(str, Enum):
    TEXT = "text"
    PHOTO = "photo"


class BroadcastButtonType(str, Enum):
    NONE = "none"
    URL = "url"
    INTERNAL_ACTION = "internal_action"


class BroadcastStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TopupStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class InventoryStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    DELETED = "deleted"


class BalanceTransactionType(str, Enum):
    TOPUP = "topup"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class CheckoutSessionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
