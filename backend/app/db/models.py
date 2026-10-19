"""Relational schema.

products 1──1 inventory          stock lives in its own row so hot writes to
    │                            stock never touch catalogue data
    ├──< cart_items >── carts
    └──< order_items >── orders ──< order_events   (status history)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


def str_enum(enum_cls: type[StrEnum]) -> Enum:
    """Store the enum's *value* ("placed") as VARCHAR. Portable across SQLite
    and Postgres and easy to read in raw SQL. The allowed values are enforced
    by an explicit, uniquely named CHECK constraint on each table (see
    ``enum_check``) rather than ``create_constraint=True``, which Alembic
    renders more than once on Postgres."""
    return Enum(
        enum_cls,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
    )


def enum_check(column: str, enum_cls: type[StrEnum], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{m.value}'" for m in enum_cls)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class Base(DeclarativeBase):
    pass


class OrderStatus(StrEnum):
    PLACED = "placed"  # paid, stock reserved, waiting for a robot
    PICKING = "picking"
    PACKING = "packing"
    SHIPPED = "shipped"


class CartStatus(StrEnum):
    OPEN = "open"
    CHECKED_OUT = "checked_out"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price_cents >= 0", name="ck_products_price_nonneg"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), index=True)
    image_url: Mapped[str | None] = mapped_column(String(300))
    price_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inventory: Mapped[Inventory] = relationship(back_populates="product", uselist=False)


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_inventory_quantity_nonneg"),)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    product: Mapped[Product] = relationship(back_populates="inventory")


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (enum_check("status", CartStatus, "ck_carts_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    status: Mapped[CartStatus] = mapped_column(str_enum(CartStatus), default=CartStatus.OPEN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan", order_by="CartItem.product_id"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_cart_items_quantity_pos"),)

    cart_id: Mapped[str] = mapped_column(
        ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)

    cart: Mapped[Cart] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # The dispatcher polls for "placed and not yet sent to the simulation".
        Index("ix_orders_status_dispatched", "status", "dispatched_at"),
        CheckConstraint("total_cents >= 0", name="ck_orders_total_nonneg"),
        enum_check("status", OrderStatus, "ck_orders_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid)
    # Unique constraint = the database itself rejects a duplicate submission,
    # even if two identical requests race each other.
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)
    request_hash: Mapped[str | None] = mapped_column(String(64))
    customer_email: Mapped[str] = mapped_column(String(254))
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), default=OrderStatus.PLACED)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    events: Mapped[list[OrderEvent]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderEvent.id"
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_order_items_quantity_pos"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    # Price is copied at purchase time: later catalogue edits must not change
    # what the customer was charged.
    unit_price_cents: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (enum_check("status", OrderStatus, "ck_order_events_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus))
    message: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    order: Mapped[Order] = relationship(back_populates="events")
