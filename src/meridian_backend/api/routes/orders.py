from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from meridian_backend.api.dependencies import get_customers, get_orders, get_products, get_order_service
from meridian_backend.api.mappers import to_order_response
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.models.product import Product
from meridian_backend.schemas.order import CreateOrder, OrderResponse
from meridian_backend.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse])
def list_orders(
    orders: Annotated[list[Order], Depends(get_orders)],
) -> list[OrderResponse]:
    return [to_order_response(order) for order in OrderService().list_orders(orders)]


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: CreateOrder,
    orders: Annotated[list[Order], Depends(get_orders)],
    customers: Annotated[list[Customer], Depends(get_customers)],
    products: Annotated[list[Product], Depends(get_products)],
) -> OrderResponse:
    order = OrderService().create_order(
        orders=orders,
        customers=customers,
        products=products,
        customer_id=payload.customer_id,
        items=[(item.product_id, item.quantity) for item in payload.items],
    )
    return to_order_response(order)


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: UUID,
    orders: Annotated[list[Order], Depends(get_orders)],
    service: Annotated[OrderService, Depends(get_order_service)]
) -> OrderResponse:
    order = service.get_order_by_id(orders, order_id)
    return to_order_response(order)
