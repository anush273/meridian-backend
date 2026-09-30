from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.api.exception_handlers import register_exception_handlers
from meridian_backend.core.config import Settings
from meridian_backend.core.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    WrongPasswordError,
)
from meridian_backend.core.security import hash_password
from meridian_backend.models.user import User
from meridian_backend.repositories.user_repository import UserRepository
from meridian_backend.services.auth_service import AuthService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario", ["valid", "missing", "wrong_password", "inactive", "inactive_wrong"]
)
async def test_authenticate(scenario):
    user = User(
        id=uuid4(),
        name="Test",
        email="test@example.com",
        password_hash=hash_password("correct password"),
        role="CUSTOMER",
        is_active=not scenario.startswith("inactive"),
    )
    repository = AsyncMock(spec=UserRepository)
    repository.get_by_email.return_value = None if scenario == "missing" else user
    service = AuthService(
        repository,
        AsyncMock(spec=AsyncSession),
        Settings(
            _env_file=None,
            database_url="sqlite://",
            jwt_secret_key="test-key-with-at-least-32-characters",
        ),
    )
    password = (
        "wrong password" if scenario in ("wrong_password", "inactive_wrong") else "correct password"
    )
    if scenario == "valid":
        assert await service.authenticate(user.email, password) is user
    else:
        expected = {
            "inactive": InactiveUserError,
            "missing": InvalidCredentialsError,
            "wrong_password": WrongPasswordError,
            "inactive_wrong": WrongPasswordError,
        }[scenario]
        with pytest.raises(expected):
            await service.authenticate(user.email, password)
    repository.get_by_email.assert_awaited_once_with(user.email)
    repository.add.assert_not_awaited()


@pytest.mark.parametrize(
    "error,status,message",
    [
        (InvalidCredentialsError(), 401, "Invalid email or password"),
        (WrongPasswordError(), 401, "Invalid email or password"),
        (InactiveUserError(), 403, "User account is inactive"),
    ],
)
def test_auth_exception_http_response(error, status, message):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/test")
    async def fail():
        raise error

    with TestClient(app) as client:
        response = client.get("/test")
    assert response.status_code == status
    assert response.json() == {"detail": message}
