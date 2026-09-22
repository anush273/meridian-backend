from decimal import Decimal
from uuid import UUID, uuid4

from meridian_backend.core.exceptions import (
    CustomerNotFoundError,
    OrderNotFoundError,
    ProductNotFoundError,
)
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order, OrderItem
from meridian_backend.models.product import Product


class OrderService:
    def __init__(self, orders: list[Order], customers: list[Customer], products: list[Product]):
        self.orders = orders
        self.customers = customers
        self.products = products

    def list_orders(self) -> list[Order]:
        return list(self.orders)

    def create_order(
        self,
        customer_id: UUID,
        items: list[tuple[UUID, int]],
    ) -> Order:
        customer = next((c for c in self.customers if c.id == customer_id), None)
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        products_by_id = {product.id: product for product in self.products}
        order_items: list[OrderItem] = []
        for product_id, quantity in items:
            product = products_by_id.get(product_id)
            if product is None:
                raise ProductNotFoundError(product_id)
            order_items.append(OrderItem(product=product, quantity=quantity))
        order = Order(id=uuid4(), customer=customer, items=order_items)
        self.orders.append(order)
        return order

    def get_paid_orders(self) -> list[Order]:
        return [order for order in self.orders if order.status == "PAID"]

    def calculate_revenue(self) -> Decimal:
        return sum((order.total() for order in self.get_paid_orders()), Decimal("0"))

    def get_orders_by_customer(
        self,
        customer_id: UUID,
    ) -> list[Order]:
        return [order for order in self.orders if order.customer.id == customer_id]

    def get_highest_order(self) -> Order:
        return max(self.orders, key=lambda order: order.total())

    def get_order_by_id(self, order_id: UUID) -> Order:
        for order in self.orders:
            if order.id == order_id:
                return order
        raise OrderNotFoundError(order_id)
