from uuid import uuid4

import pytest

from meridian_backend.core.exceptions import OrderNotFoundError
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.services.order_service import OrderService


def test_get_order_by_id_returns_exact_object(customer: Customer) -> None:
    other = Order(id=uuid4(), customer=customer, status="PENDING")
    expected = Order(id=uuid4(), customer=customer, status="PAID")

    result = OrderService().get_order_by_id([other, expected], expected.id)

    assert result is expected


def test_get_order_by_id_missing_order_raises_with_order_id(customer: Customer) -> None:
    existing = Order(id=uuid4(), customer=customer, status="PENDING")
    missing_id = uuid4()

    with pytest.raises(OrderNotFoundError) as exc_info:
        OrderService().get_order_by_id([existing], missing_id)

    assert exc_info.value.order_id == missing_id
