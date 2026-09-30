from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from meridian_backend.db.models import IdempotencyRecordModel, OrderModel
from meridian_backend.main import app
from meridian_backend.models.product import Product


def test_authenticated_order_creation_commits_and_replays(database, customer, seed):
    product = Product(id=uuid4(), name="Book", price=Decimal("25.00"))
    seed([customer], [product], [])
    credentials = {"email": "order-test@example.com", "password": "test-password-123"}
    with TestClient(app) as client:
        assert client.post("/register", json={"name": "Test", **credentials}).status_code == 201
        login = client.post("/login", json=credentials)
        assert login.status_code == 200
        headers = {
            "Authorization": f"Bearer {login.json()['access_token']}",
            "Idempotency-key": str(uuid4()),
        }
        payload = {
            "customer_id": str(customer.id),
            "items": [{"product_id": str(product.id), "quantity": 1}],
        }
        failed = client.post(
            "/orders",
            json={**payload, "items": [{"product_id": str(uuid4()), "quantity": 1}]},
            headers=headers,
        )
        assert failed.status_code == 404
        with Session(database) as session:
            assert session.scalar(select(func.count()).select_from(OrderModel)) == 0
            assert session.scalar(select(func.count()).select_from(IdempotencyRecordModel)) == 0
        response = client.post("/orders", json=payload, headers=headers)
        assert response.status_code == 201
        replay = client.post("/orders", json=payload, headers=headers)
        assert replay.status_code == 201
        assert replay.json() == response.json()
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(OrderModel)) == 1
        assert session.scalar(select(func.count()).select_from(IdempotencyRecordModel)) == 1
