"""Order placement: the one place where money and inventory change together.

Correctness rules this module guarantees:

* **No overselling.** Stock is decremented with a conditional UPDATE
  (``... SET quantity = quantity - :q WHERE product_id = :p AND quantity >= :q``).
  The check and the write are one atomic statement, so two buyers racing for
  the last unit cannot both succeed: the second UPDATE matches zero rows.
* **All or nothing.** Every stock decrement and the order rows are written in a
  single transaction. If any line is out of stock, everything rolls back.
* **Deadlock-free locking order.** Lines are processed in ascending product id,
  so two orders that share products always lock rows in the same order.
* **Idempotent retries.** An ``Idempotency-Key`` is stored under a UNIQUE
  constraint. A retried request returns the original order instead of
  charging twice, even if the two requests arrive at the same instant.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult, Result
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Cart,
    CartStatus,
    Inventory,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    Product,
)
from app.schemas import OrderCreate, OrderEventOut, OrderLineOut, OrderOut, OrderSummary
from app.services.errors import (
    CartClosed,
    EmptyCart,
    IdempotencyMismatch,
    NotFound,
    OutOfStock,
)

log = logging.getLogger(__name__)


def rowcount(result: Result[Any]) -> int:
    """Rows matched by an UPDATE. (DML returns a CursorResult at runtime.)"""
    return cast(CursorResult[Any], result).rowcount


@dataclass
class PlaceOrderResult:
    order: OrderOut
    created: bool  # False when an idempotent replay returned an existing order


def request_fingerprint(body: OrderCreate) -> str:
    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def place_order(
    session: Session, body: OrderCreate, idempotency_key: str | None = None
) -> PlaceOrderResult:
    fingerprint = request_fingerprint(body)

    if idempotency_key:
        existing = _find_by_key(session, idempotency_key)
        if existing is not None:
            return _replay(session, existing, fingerprint)

    try:
        order = _create(session, body, idempotency_key, fingerprint)
        session.commit()
    except IntegrityError:
        # Lost a race with an identical request that committed first: the
        # UNIQUE(idempotency_key) constraint fired. Our transaction (including
        # its stock decrements) is rolled back, so nothing was double-counted.
        session.rollback()
        if idempotency_key and (existing := _find_by_key(session, idempotency_key)):
            return _replay(session, existing, fingerprint)
        raise
    except Exception:
        session.rollback()
        raise

    log.info("order placed", extra={"order_id": order.public_id, "total": order.total_cents})
    return PlaceOrderResult(order=get_order(session, order.public_id), created=True)


def _create(session: Session, body: OrderCreate, key: str | None, fingerprint: str) -> Order:
    cart: Cart | None = None
    if body.cart_id is not None:
        cart = session.get(Cart, body.cart_id)
        if cart is None:
            raise NotFound(f"cart {body.cart_id} not found")
        lines = {i.product_id: i.quantity for i in cart.items}
    else:
        assert body.items is not None
        lines = {i.product_id: i.quantity for i in body.items}
    if not lines:
        raise EmptyCart("cannot place an order with no items")

    products = {
        p.id: p for p in session.scalars(select(Product).where(Product.id.in_(lines.keys())))
    }
    missing = sorted(set(lines) - set(products))
    if missing:
        raise NotFound(f"unknown product id(s): {missing}")

    for product_id in sorted(lines):  # consistent lock order
        qty = lines[product_id]
        result = session.execute(
            update(Inventory)
            .where(Inventory.product_id == product_id, Inventory.quantity >= qty)
            .values(quantity=Inventory.quantity - qty)
        )
        if rowcount(result) == 0:
            available = session.scalar(
                select(Inventory.quantity).where(Inventory.product_id == product_id)
            )
            raise OutOfStock(
                f"not enough stock for {products[product_id].name}",
                product_id=product_id,
                requested=qty,
                available=available or 0,
            )

    if cart is not None:
        # Conditional update: a cart can only be checked out once, even if two
        # checkout requests for the same cart race.
        closed = session.execute(
            update(Cart)
            .where(Cart.id == cart.id, Cart.status == CartStatus.OPEN)
            .values(status=CartStatus.CHECKED_OUT)
        )
        if rowcount(closed) == 0:
            raise CartClosed("cart has already been checked out")

    order = Order(
        idempotency_key=key,
        request_hash=fingerprint,
        customer_email=body.customer_email,
        status=OrderStatus.PLACED,
        total_cents=sum(products[pid].price_cents * q for pid, q in lines.items()),
        items=[
            OrderItem(product_id=pid, quantity=q, unit_price_cents=products[pid].price_cents)
            for pid, q in sorted(lines.items())
        ],
        events=[OrderEvent(status=OrderStatus.PLACED, message="Order placed, stock reserved")],
    )
    session.add(order)
    session.flush()  # surfaces UNIQUE violations inside the try block
    return order


def _find_by_key(session: Session, key: str) -> Order | None:
    return session.scalar(select(Order).where(Order.idempotency_key == key))


def _replay(session: Session, order: Order, fingerprint: str) -> PlaceOrderResult:
    if order.request_hash != fingerprint:
        raise IdempotencyMismatch(
            "this Idempotency-Key was already used with a different request body"
        )
    return PlaceOrderResult(order=get_order(session, order.public_id), created=False)


# ---------------------------------------------------------------------- reads


def get_order(session: Session, public_id: str) -> OrderOut:
    order = session.scalar(
        select(Order)
        .where(Order.public_id == public_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.events),
        )
    )
    if order is None:
        raise NotFound(f"order {public_id} not found")
    return OrderOut(
        id=order.public_id,
        status=order.status,
        customer_email=order.customer_email,
        total_cents=order.total_cents,
        created_at=order.created_at,
        shipped_at=order.shipped_at,
        items=[
            OrderLineOut(
                product_id=i.product_id,
                sku=i.product.sku,
                name=i.product.name,
                image_url=i.product.image_url,
                quantity=i.quantity,
                unit_price_cents=i.unit_price_cents,
            )
            for i in order.items
        ],
        events=[OrderEventOut.model_validate(e) for e in order.events],
    )


def list_orders(
    session: Session, status: OrderStatus | None = None, limit: int = 50
) -> list[OrderSummary]:
    item_count = (
        select(OrderItem.order_id, func.sum(OrderItem.quantity).label("n"))
        .group_by(OrderItem.order_id)
        .subquery()
    )
    stmt = (
        select(Order, item_count.c.n)
        .join(item_count, item_count.c.order_id == Order.id)
        .order_by(Order.id.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Order.status == status)
    return [
        OrderSummary(
            id=o.public_id,
            status=o.status,
            total_cents=o.total_cents,
            item_count=int(n),
            created_at=o.created_at,
        )
        for o, n in session.execute(stmt).all()
    ]


def order_stats(session: Session) -> dict:
    by_status = dict(
        session.execute(select(Order.status, func.count()).group_by(Order.status)).all()
    )
    revenue = session.scalar(select(func.coalesce(func.sum(Order.total_cents), 0)))
    units_in_stock = session.scalar(select(func.coalesce(func.sum(Inventory.quantity), 0)))
    return {
        "orders_by_status": {s.value: by_status.get(s, 0) for s in OrderStatus},
        "revenue_cents": int(revenue or 0),
        "units_in_stock": int(units_in_stock or 0),
    }
