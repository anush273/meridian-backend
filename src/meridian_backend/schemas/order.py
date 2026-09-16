from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

OrderStatus = Literal["PENDING", "PAID", "FAILED"]


class CreateOrderItem(BaseModel):
    product_id: UUID
    quantity: int = Field(gt=0, strict=True)


class CreateOrder(BaseModel):
    items: list[CreateOrderItem] = Field(min_length=1)
    status: OrderStatus = "PENDING"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrderUpdate(BaseModel):
    items: list[CreateOrderItem] | None = Field(default=None, min_length=1)
    status: OrderStatus | None = None
 


class OrderItemResponse(CreateOrderItem):
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    subtotal: Decimal = Field(ge=0, allow_inf_nan=False)


class OrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    items: list[OrderItemResponse] = Field(min_length=1)
    status: OrderStatus
    subtotal: Decimal = Field(ge=0, allow_inf_nan=False)
    tax: Decimal = Field(ge=0, allow_inf_nan=False)
    total: Decimal = Field(ge=0, allow_inf_nan=False)
    createdAt: datetime
    updatedAt: datetime | None = None
