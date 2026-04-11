from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, ButtonActionType, Language, OrderStatus, PaymentProviderType, ProductStatus, utcnow


enum_language = Enum(Language, native_enum=False, length=8)
enum_order_status = Enum(OrderStatus, native_enum=False, length=32)
enum_payment_type = Enum(PaymentProviderType, native_enum=False, length=16)
enum_button_action = Enum(ButtonActionType, native_enum=False, length=16)
enum_product_status = Enum(ProductStatus, native_enum=False, length=16)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[Language] = mapped_column(enum_language, default=Language.RU)
    language_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)

    orders: Mapped[list["Order"]] = relationship(back_populates="user", lazy="selectin")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    translations: Mapped[list["CategoryTranslation"]] = relationship(back_populates="category", cascade="all, delete-orphan", lazy="selectin")
    products: Mapped[list["Product"]] = relationship(back_populates="category", lazy="selectin")


class CategoryTranslation(Base):
    __tablename__ = "category_translations"
    __table_args__ = (UniqueConstraint("category_id", "language", name="uq_category_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    language: Mapped[Language] = mapped_column(enum_language)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped["Category"] = relationship(back_populates="translations", lazy="selectin")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[ProductStatus] = mapped_column(enum_product_status, default=ProductStatus.ACTIVE)
    delivery_type: Mapped[str] = mapped_column(String(32), default="manual")
    workflow_type: Mapped[str] = mapped_column(String(64), default="manual")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(8), default="UZS")
    photo_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    show_in_catalog: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    category: Mapped["Category | None"] = relationship(back_populates="products", lazy="selectin")
    translations: Mapped[list["ProductTranslation"]] = relationship(back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    payment_links: Mapped[list["ProductPaymentMethod"]] = relationship(back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    orders: Mapped[list["Order"]] = relationship(back_populates="product", lazy="selectin")


class ProductTranslation(Base):
    __tablename__ = "product_translations"
    __table_args__ = (UniqueConstraint("product_id", "language", name="uq_product_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    language: Mapped[Language] = mapped_column(enum_language)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")

    product: Mapped["Product"] = relationship(back_populates="translations", lazy="selectin")


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider_type: Mapped[PaymentProviderType] = mapped_column(enum_payment_type, default=PaymentProviderType.OTHER)
    admin_title: Mapped[str] = mapped_column(String(255))
    credentials: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    photo_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    translations: Mapped[list["PaymentMethodTranslation"]] = relationship(back_populates="payment_method", cascade="all, delete-orphan", lazy="selectin")
    product_links: Mapped[list["ProductPaymentMethod"]] = relationship(back_populates="payment_method", cascade="all, delete-orphan", lazy="selectin")
    orders: Mapped[list["Order"]] = relationship(back_populates="payment_method", lazy="selectin")


class PaymentMethodTranslation(Base):
    __tablename__ = "payment_method_translations"
    __table_args__ = (UniqueConstraint("payment_method_id", "language", name="uq_payment_method_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id", ondelete="CASCADE"))
    language: Mapped[Language] = mapped_column(enum_language)
    title: Mapped[str] = mapped_column(String(255))
    instructions: Mapped[str] = mapped_column(Text, default="")

    payment_method: Mapped["PaymentMethod"] = relationship(back_populates="translations", lazy="selectin")


class ProductPaymentMethod(Base):
    __tablename__ = "product_payment_methods"
    __table_args__ = (UniqueConstraint("product_id", "payment_method_id", name="uq_product_payment_method"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    payment_method_id: Mapped[int] = mapped_column(ForeignKey("payment_methods.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped["Product"] = relationship(back_populates="payment_links", lazy="selectin")
    payment_method: Mapped["PaymentMethod"] = relationship(back_populates="product_links", lazy="selectin")


class TextEntry(Base):
    __tablename__ = "texts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    group_name: Mapped[str] = mapped_column(String(64), default="general")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    translations: Mapped[list["TextTranslation"]] = relationship(back_populates="text_entry", cascade="all, delete-orphan", lazy="selectin")


class TextTranslation(Base):
    __tablename__ = "text_translations"
    __table_args__ = (UniqueConstraint("text_id", "language", name="uq_text_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    text_id: Mapped[int] = mapped_column(ForeignKey("texts.id", ondelete="CASCADE"))
    language: Mapped[Language] = mapped_column(enum_language)
    value: Mapped[str] = mapped_column(Text, default="")

    text_entry: Mapped["TextEntry"] = relationship(back_populates="translations", lazy="selectin")


class Layout(Base):
    __tablename__ = "layouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(32), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    buttons: Mapped[list["LayoutButton"]] = relationship(back_populates="layout", cascade="all, delete-orphan", lazy="selectin")


class LayoutButton(Base):
    __tablename__ = "buttons"
    __table_args__ = (UniqueConstraint("layout_id", "code", name="uq_layout_button_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    layout_id: Mapped[int] = mapped_column(ForeignKey("layouts.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))
    action_type: Mapped[ButtonActionType] = mapped_column(enum_button_action, default=ButtonActionType.CALLBACK)
    action_value: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[str] = mapped_column(String(32), default="default")
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    layout: Mapped["Layout"] = relationship(back_populates="buttons", lazy="selectin")
    translations: Mapped[list["LayoutButtonTranslation"]] = relationship(back_populates="button", cascade="all, delete-orphan", lazy="selectin")


class LayoutButtonTranslation(Base):
    __tablename__ = "button_translations"
    __table_args__ = (UniqueConstraint("button_id", "language", name="uq_button_translation"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    button_id: Mapped[int] = mapped_column(ForeignKey("buttons.id", ondelete="CASCADE"))
    language: Mapped[Language] = mapped_column(enum_language)
    text: Mapped[str] = mapped_column(String(255))

    button: Mapped["LayoutButton"] = relationship(back_populates="translations", lazy="selectin")


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    value_type: Mapped[str] = mapped_column(String(32), default="string")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("payment_methods.id", ondelete="SET NULL"), nullable=True)
    product_code_snapshot: Mapped[str] = mapped_column(String(64), default="")
    product_name_snapshot: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(8), default="UZS")
    status: Mapped[OrderStatus] = mapped_column(enum_order_status, default=OrderStatus.PENDING_PAYMENT, index=True)
    workflow_type: Mapped[str] = mapped_column(String(64), default="manual")
    delivery_type: Mapped[str] = mapped_column(String(32), default="manual")
    language: Mapped[str] = mapped_column(String(8), default="ru")
    customer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    payment_proof_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_proof_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="orders", lazy="selectin")
    product: Mapped["Product | None"] = relationship(back_populates="orders", lazy="selectin")
    payment_method: Mapped["PaymentMethod | None"] = relationship(back_populates="orders", lazy="selectin")
    history: Mapped[list["OrderStatusHistory"]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    capcut_account: Mapped["CapCutAccount | None"] = relationship(back_populates="issued_order", lazy="selectin")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[OrderStatus | None] = mapped_column(enum_order_status, nullable=True)
    to_status: Mapped[OrderStatus] = mapped_column(enum_order_status)
    changed_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped["Order"] = relationship(back_populates="history", lazy="selectin")


class CapCutAccount(Base):
    __tablename__ = "capcut_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(255))
    password: Mapped[str] = mapped_column(String(255))
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    issued_to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    issued_order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, unique=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow)
    issued_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    issued_order: Mapped["Order | None"] = relationship(back_populates="capcut_account", lazy="selectin")
