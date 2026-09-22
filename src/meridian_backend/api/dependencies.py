from fastapi import Request,Depends
from typing import Annotated

from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.models.product import Product

from meridian_backend.services.order_service import OrderService

from meridian_backend.core.config import Settings, get_settings


def get_orders(request: Request) -> list[Order]:
    """Return the application's temporary, in-memory order collection."""
    return request.app.state.orders


def get_customers(request: Request) -> list[Customer]:
    return request.app.state.customers


def get_products(request: Request) -> list[Product]:
    return request.app.state.products


def get_order_service(orders: Annotated[list[Order], Depends(get_orders)], customers: Annotated[list[Customer], Depends(get_customers)], products: Annotated[list[Product], Depends(get_products)]) -> OrderService:
    return OrderService(orders,customers,products)

SettingService = Annotated[Settings,Depends(get_settings)]