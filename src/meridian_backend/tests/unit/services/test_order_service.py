from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from meridian_backend.core.exceptions import OrderNotFoundError
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order, OrderItem
from meridian_backend.models.product import Product
from meridian_backend.repositories.order_repository import OrderRepository
from meridian_backend.services.order_service import OrderService

pytestmark = pytest.mark.asyncio


async def test_get_order_by_id_returns_exact_object(customer: Customer) -> None:
    expected = Order(id=uuid4(), customer=customer, status="PAID")

    repository = AsyncMock(spec=OrderRepository)
    repository.get_by_id.return_value = expected
    result = await OrderService(repository).get_order_by_id(expected.id)

    assert result is expected


async def test_get_order_by_id_missing_order_raises_with_order_id(customer: Customer) -> None:
    repository = AsyncMock(spec=OrderRepository)
    repository.get_by_id.return_value = None
    missing_id = uuid4()

    with pytest.raises(OrderNotFoundError) as exc_info:
        await OrderService(repository).get_order_by_id(missing_id)

    assert exc_info.value.order_id == missing_id


async def test_revenue_uses_exact_decimal_totals_for_paid_orders(customer: Customer) -> None:
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
    repository = AsyncMock(spec=OrderRepository)
    repository.list_orders.return_value = [paid, pending]
    service = OrderService(repository)

    assert paid.subtotal() == Decimal("0.30")
    assert paid.tax() == Decimal("0.054")
    assert paid.total() == Decimal("0.354")
    assert paid.total(Decimal("0.20")) == Decimal("0.36")
    assert await service.calculate_revenue() == Decimal("0.354")


async def test_empty_revenue_is_decimal_zero() -> None:
    repository = AsyncMock(spec=OrderRepository)
    repository.list_orders.return_value = []
    revenue = await OrderService(repository).calculate_revenue()

    assert isinstance(revenue, Decimal)
    assert revenue == Decimal("0")
