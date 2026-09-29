from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from meridian_backend.core.security import verify_password
from meridian_backend.db.models import UserModel
from meridian_backend.main import app
from meridian_backend.repositories.user_repository import UserRepository


@pytest.fixture
def payload():
    return {"name": " Test User ", "email": "test@example.com", "password": "password with spaces "}


def test_registration_persists_hash_and_returns_public_fields(database, payload):
    with TestClient(app) as client:
        response = client.post("/register", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "name", "email", "role", "is_active"}
    assert body["email"] == payload["email"]
    assert body["name"] == "Test User"
    assert body["role"] == "CUSTOMER"
    assert body["is_active"] is True
    with Session(database) as session:
        user = session.scalar(select(UserModel))
        assert str(user.id) == body["id"]
        assert user.password_hash != payload["password"]
        assert verify_password(payload["password"], user.password_hash)


@pytest.mark.parametrize("miss_precheck", [False, True])
def test_duplicate_email_returns_conflict(database, payload, monkeypatch, miss_precheck):
    with TestClient(app) as client:
        assert client.post("/register", json=payload).status_code == 201
        if miss_precheck:
            # Reproduce the stale lookup in two racing requests; the real DB rejects the insert.
            monkeypatch.setattr(UserRepository, "get_by_email", AsyncMock(return_value=None))
        assert client.post("/register", json=payload).status_code == 409
        payload["email"] = "another@example.com"
        assert client.post("/register", json=payload).status_code == 201
    with Session(database) as session:
        assert len(session.scalars(select(UserModel)).all()) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "a" * 201),
        ("password", ""),
        ("password", "short"),
        ("password", "a" * 129),
        ("email", "invalid"),
    ],
)
def test_invalid_registration_does_not_persist(database, payload, field, value):
    payload[field] = value
    with TestClient(app) as client:
        assert client.post("/register", json=payload).status_code == 422
    with Session(database) as session:
        assert session.scalar(select(UserModel)) is None


def test_login_returns_registered_user(payload):
    with TestClient(app) as client:
        registered = client.post("/register", json=payload)
        response = client.post(
            "/login",
            json={
                "email": payload["email"],
                "password": payload["password"],
            },
        )
    assert registered.status_code == 201
    assert response.status_code == 200
    assert response.json() == registered.json()
    assert "password_hash" not in response.json()


@pytest.mark.parametrize("missing", [False, True])
def test_login_invalid_credentials(payload, missing):
    with TestClient(app) as client:
        if not missing:
            assert client.post("/register", json=payload).status_code == 201
        response = client.post(
            "/login",
            json={
                "email": payload["email"],
                "password": "incorrect password",
            },
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_login_inactive_user(database, payload):
    with TestClient(app) as client:
        assert client.post("/register", json=payload).status_code == 201
        with Session(database) as session:
            user = session.scalar(select(UserModel))
            user.is_active = False
            session.commit()
        response = client.post(
            "/login",
            json={
                "email": payload["email"],
                "password": payload["password"],
            },
        )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": "bad", "password": "password"},
        {"email": "test@example.com", "password": ""},
        {"email": "test@example.com", "password": "x" * 129},
    ],
)
def test_login_invalid_payload(payload):
    with TestClient(app) as client:
        assert client.post("/login", json=payload).status_code == 422
