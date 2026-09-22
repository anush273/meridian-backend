from decimal import Decimal
from uuid import uuid4

import pytest

from meridian_backend.core.exceptions import OrderNotFoundError
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order, OrderItem
from meridian_backend.models.product import Product
from meridian_backend.services.order_service import OrderService


def test_get_order_by_id_returns_exact_object(customer: Customer) -> None:
    other = Order(id=uuid4(), customer=customer, status="PENDING")
    expected = Order(id=uuid4(), customer=customer, status="PAID")

    result = OrderService([other, expected], [customer], []).get_order_by_id(expected.id)

    assert result is expected


def test_get_order_by_id_missing_order_raises_with_order_id(customer: Customer) -> None:
    existing = Order(id=uuid4(), customer=customer, status="PENDING")
    missing_id = uuid4()

    with pytest.raises(OrderNotFoundError) as exc_info:
        OrderService([existing], [customer], []).get_order_by_id(missing_id)

    assert exc_info.value.order_id == missing_id


def test_revenue_uses_exact_decimal_totals_for_paid_orders(customer: Customer) -> None:
    product = Product(id=uuid4(), name="Small item", price=Decimal("0.10"))
    paid = Order(
        id=uuid4(),
        customer=customer,
        status="PAID",
        items=[OrderItem(product=product, quantity=3)],
    )
    pending = Order(
        id=uuid4(),
        customer=customer,
        items=[OrderItem(product=product, quantity=10)],
    )
    service = OrderService([paid, pending], [customer], [product])

    assert paid.subtotal() == Decimal("0.30")
    assert paid.tax() == Decimal("0.054")
    assert paid.total() == Decimal("0.354")
    assert paid.total(Decimal("0.20")) == Decimal("0.36")
    assert service.calculate_revenue() == Decimal("0.354")


def test_empty_revenue_is_decimal_zero() -> None:
    revenue = OrderService([], [], []).calculate_revenue()

    assert isinstance(revenue, Decimal)
    assert revenue == Decimal("0")
