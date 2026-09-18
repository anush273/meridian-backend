from meridian_backend.models.order import Order
from meridian_backend.core.exceptions import OrderNotFoundError

from uuid import UUID


class OrderService:
    def get_paid_orders(
        self,
        orders: list[Order],
    ) -> list[Order]:
        return [order for order in orders if order.status == "PAID"]

    def calculate_revenue(
        self,
        orders: list[Order],
    ) -> float:
        return sum(
            (order.total() for order in self.get_paid_orders(orders)),
            0.0,
        )

    def get_orders_by_customer(
        self,
        orders: list[Order],
        customer_id: int,
    ) -> list[Order]:
        return [order for order in orders if order.customer.id == customer_id]
    
    def get_highest_order(self, orders: list[Order]) -> Order:
        return max(orders, key=lambda order: order.total())

    def get_order_by_id(self, orders: list[Order], order_id: UUID) -> Order:
        for order in orders:
            if order.id == order_id:
                return order
        raise OrderNotFoundError(order_id)