from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from meridian_backend.main import app
from meridian_backend.models.product import Product


@pytest.fixture
def collection(customer, seed):
    product = Product(id=uuid4(), name="Book", price=Decimal("25.00"))
    seed([customer], [product], [])
    payload = {
        "customer_id": str(customer.id),
        "items": [{"product_id": str(product.id), "quantity": 2}],
    }
    with TestClient(app) as client:
        yield client, payload


def test_list_empty(collection):
    client, _ = collection
    response = client.get("/orders")
    assert response.status_code == 200
    assert response.json() == []


def test_create_then_list_and_get(collection):
    client, payload = collection
    response = client.post("/orders", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["customer_id"] == payload["customer_id"]
    assert body["status"] == "PENDING"
    assert body["items"][0]["product_id"] == payload["items"][0]["product_id"]
    assert body["items"][0]["quantity"] == 2
    assert body["subtotal"] == "50.00"
    assert body["tax"] == "9.0000"
    assert body["total"] == "59.0000"
    assert client.get("/orders").json() == [body]
    assert client.get(f"/orders/{body['id']}").json() == body
    second = client.post("/orders", json=payload)
    assert second.status_code == 201
    assert second.json()["id"] != body["id"]
    assert client.get("/orders").json() == [body, second.json()]


@pytest.mark.parametrize("missing", ["customer", "product"])
def test_missing_reference_does_not_create_order(collection, missing):
    client, payload = collection
    missing_id = str(uuid4())
    if missing == "customer":
        payload["customer_id"] = missing_id
    else:
        payload["items"].append({"product_id": missing_id, "quantity": 1})
    response = client.post("/orders", json=payload)
    assert response.status_code == 404
    assert missing_id in response.json()["detail"]
    assert client.get("/orders").json() == []


@pytest.mark.parametrize("invalid", ["empty", "quantity", "customer", "status", "timestamp"])
def test_invalid_create_request(collection, invalid):
    client, payload = collection
    if invalid == "empty":
        payload["items"] = []
    elif invalid == "quantity":
        payload["items"][0]["quantity"] = 0
    elif invalid == "customer":
        del payload["customer_id"]
    elif invalid == "status":
        payload["status"] = "PAID"
    else:
        payload["created_at"] = "2026-01-01T00:00:00Z"
    assert client.post("/orders", json=payload).status_code == 422
    assert client.get("/orders").json() == []
