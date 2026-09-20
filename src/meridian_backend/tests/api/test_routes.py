from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from meridian_backend.api.dependencies import get_orders
from meridian_backend.main import app
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order, OrderItem
from meridian_backend.models.product import Product


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.parametrize("with_items", [True, False])
def test_get_order(client: TestClient, customer: Customer, with_items: bool) -> None:
    product = Product(id=uuid4(), name="Notebook", price=10.0)
    order = Order(
        id=uuid4(),
        customer=customer,
        status="PENDING",
        items=[OrderItem(product=product, quantity=2)] if with_items else [],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    app.dependency_overrides[get_orders] = lambda: [order]
    try:
        response = client.get(f"/orders/{order.id}")
        repeated = client.get(f"/orders/{order.id}")
    finally:
        del app.dependency_overrides[get_orders]

    assert response.status_code == 200
    assert response.json() == {
        "id": str(order.id),
        "customer_id": str(customer.id),
        "items": [
            {
                "product_id": str(product.id),
                "quantity": 2,
                "price": "10.0",
                "subtotal": "20.0",
            }
        ]
        if with_items
        else [],
        "status": "PENDING",
        "subtotal": "20.0" if with_items else "0.0",
        "tax": "3.5999999999999996" if with_items else "0.0",
        "total": "23.6" if with_items else "0.0",
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": None,
    }
    assert repeated.json() == response.json()


def test_missing_order_returns_404(client: TestClient) -> None:
    order_id = uuid4()

    response = client.get(f"/orders/{order_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": f"Order {order_id} not found"}


def test_invalid_order_id_returns_422(client: TestClient) -> None:
    response = client.get("/orders/not-a-uuid")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "order_id"]


def test_unexpected_error_returns_generic_500(caplog: pytest.LogCaptureFixture) -> None:
    def failing_orders() -> list[Order]:
        raise RuntimeError("Private failure details")

    app.dependency_overrides[get_orders] = failing_orders
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/orders")
    finally:
        del app.dependency_overrides[get_orders]

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "Private failure details" in caplog.text


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/unknown")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
