"""Pydantic models: the API's public contract (separate from the DB schema)."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.db.models import OrderStatus


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str
    category: str
    image_url: str | None
    price_cents: int
    stock: int


class CartItemIn(BaseModel):
    quantity: int = Field(ge=0, le=99, description="0 removes the item")


class CartLineOut(BaseModel):
    product: ProductOut
    quantity: int
    line_total_cents: int


class CartOut(BaseModel):
    id: str
    status: str
    items: list[CartLineOut]
    total_cents: int


class OrderLineIn(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=99)


class OrderCreate(BaseModel):
    """Place an order from a server-side cart *or* an explicit list of items."""

    customer_email: EmailStr
    cart_id: str | None = None
    items: list[OrderLineIn] | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def exactly_one_source(self) -> Self:
        if (self.cart_id is None) == (self.items is None):
            raise ValueError("provide exactly one of cart_id or items")
        if self.items is not None:
            if not self.items:
                raise ValueError("items must not be empty")
            ids = [i.product_id for i in self.items]
            if len(ids) != len(set(ids)):
                raise ValueError("each product may appear only once")
        return self


class OrderLineOut(BaseModel):
    product_id: int
    sku: str
    name: str
    image_url: str | None
    quantity: int
    unit_price_cents: int


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: OrderStatus
    message: str
    created_at: datetime


class OrderOut(BaseModel):
    id: str
    status: OrderStatus
    customer_email: str
    total_cents: int
    created_at: datetime
    shipped_at: datetime | None
    items: list[OrderLineOut]
    events: list[OrderEventOut]


class OrderSummary(BaseModel):
    id: str
    status: OrderStatus
    total_cents: int
    item_count: int
    created_at: datetime


class Problem(BaseModel):
    """Error body shape used for every 4xx we raise ourselves."""

    detail: str
    code: str
