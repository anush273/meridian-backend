from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from meridian_backend.core.exceptions import InvalidOrderStateError

from .customer import Customer
from .product import Product


@dataclass
class OrderItem:
    product: Product
    quantity: int

    def subtotal(self) -> Decimal:
        return self.product.price * self.quantity


@dataclass
class Order:
    id: UUID
    customer: Customer
    status: str = "PENDING"
    items: list[OrderItem] = field(default_factory=list[OrderItem])
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def subtotal(self) -> Decimal:
        return sum((item.subtotal() for item in self.items), Decimal("0"))

    def tax(self, tax_rate: Decimal = Decimal("0.18")) -> Decimal:
        return self.subtotal() * tax_rate

    def total(self, tax_rate: Decimal = Decimal("0.18")) -> Decimal:
        return self.subtotal() + self.tax(tax_rate)

    def mark_paid(self) -> None:
        if self.status != "PENDING":
            raise InvalidOrderStateError(
                order_id=self.id, current_status=self.status, attempted_operation="mark_paid"
            )
        self.status = "PAID"
