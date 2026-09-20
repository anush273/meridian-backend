from uuid import uuid4

import pytest

from meridian_backend.models.customer import Customer


@pytest.fixture
def customer() -> Customer:
    return Customer(id=uuid4(), name="Test Customer", email="customer@example.com")
