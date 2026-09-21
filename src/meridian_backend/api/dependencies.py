from fastapi import Request

from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.models.product import Product

from meridian_backend.services.order_service import OrderService


def get_orders(request: Request) -> list[Order]:
    """Return the application's temporary, in-memory order collection."""
    return request.app.state.orders


def get_customers(request: Request) -> list[Customer]:
    return request.app.state.customers


def get_products(request: Request) -> list[Product]:
    return request.app.state.products


def get_order_service(orders: list[Order], customers: list[Customer], products: list[Product]) -> OrderService:
    return OrderService(orders,customers,products)
