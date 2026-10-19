from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import SessionDep
from app.db.models import OrderStatus
from app.schemas import (
    CartItemIn,
    CartOut,
    OrderCreate,
    OrderOut,
    OrderSummary,
    Problem,
    ProductOut,
)
from app.services import catalog, orders
from app.services.rate_limit import limit

router = APIRouter(prefix="/api", tags=["store"])

ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": Problem},
    409: {"model": Problem},
    422: {"model": Problem},
}


@router.get("/products", response_model=list[ProductOut])
def list_products(session: SessionDep, category: str | None = None):
    return catalog.list_products(session, category)


@router.get("/products/{product_id}", response_model=ProductOut, responses=ERRORS)
def get_product(product_id: int, session: SessionDep):
    return catalog.get_product(session, product_id)


@router.post(
    "/carts",
    response_model=CartOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit("writes", "rate_limit_writes_per_min"))],
)
def create_cart(session: SessionDep):
    return catalog.create_cart(session)


@router.get("/carts/{cart_id}", response_model=CartOut, responses=ERRORS)
def get_cart(cart_id: str, session: SessionDep):
    return catalog.get_cart(session, cart_id)


@router.put("/carts/{cart_id}/items/{product_id}", response_model=CartOut, responses=ERRORS)
def set_cart_item(cart_id: str, product_id: int, body: CartItemIn, session: SessionDep):
    return catalog.set_cart_item(session, cart_id, product_id, body.quantity)


@router.delete("/carts/{cart_id}/items/{product_id}", response_model=CartOut, responses=ERRORS)
def remove_cart_item(cart_id: str, product_id: int, session: SessionDep):
    return catalog.set_cart_item(session, cart_id, product_id, 0)


@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": OrderOut, "description": "Idempotent replay"}, **ERRORS},
    dependencies=[Depends(limit("orders", "rate_limit_orders_per_min"))],
)
def place_order(
    body: OrderCreate,
    response: Response,
    session: SessionDep,
    idempotency_key: Annotated[str | None, Header(max_length=80)] = None,
):
    """Place an order. Send an `Idempotency-Key` header so that retries
    (double-clicks, network timeouts) never create a second order."""
    result = orders.place_order(session, body, idempotency_key)
    if not result.created:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
    return result.order


@router.get("/orders", response_model=list[OrderSummary])
def list_orders(
    session: SessionDep,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    return orders.list_orders(session, status_filter, limit)


@router.get("/orders/{order_id}", response_model=OrderOut, responses=ERRORS)
def get_order(order_id: str, session: SessionDep):
    return orders.get_order(session, order_id)
