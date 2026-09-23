from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from meridian_backend.api.dependencies import get_order_service
from meridian_backend.api.mappers import to_order_response
from meridian_backend.schemas.order import CreateOrder, OrderResponse
from meridian_backend.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    service: Annotated[OrderService, Depends(get_order_service)],
) -> list[OrderResponse]:
    return [to_order_response(order) for order in await service.list_orders()]


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: CreateOrder, service: Annotated[OrderService, Depends(get_order_service)]
) -> OrderResponse:
    order = await service.create_order(
        customer_id=payload.customer_id,
        items=[(item.product_id, item.quantity) for item in payload.items],
    )
    return to_order_response(order)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID, service: Annotated[OrderService, Depends(get_order_service)]
) -> OrderResponse:
    order = await service.get_order_by_id(order_id)
    return to_order_response(order)
