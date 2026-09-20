from uuid import uuid4

import pytest

from meridian_backend.core.exceptions import InvalidOrderStateError
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order


def test_mark_paid_sets_pending_order_to_paid(customer: Customer) -> None:
    order = Order(id=uuid4(), customer=customer, status="PENDING")

    order.mark_paid()

    assert order.status == "PAID"


@pytest.mark.parametrize("status", ["PAID", "FAILED"])
def test_mark_paid_rejects_non_pending_order(customer: Customer, status: str) -> None:
    order = Order(id=uuid4(), customer=customer, status=status)

    with pytest.raises(InvalidOrderStateError) as exc_info:
        order.mark_paid()

    assert order.status == status
    assert exc_info.value.order_id == order.id
    assert exc_info.value.current_status == status
