from typing import Annotated

from fastapi import APIRouter, Depends, status

from meridian_backend.api.dependencies import get_auth_service
from meridian_backend.api.mappers import to_user_response
from meridian_backend.schemas.login_user import LoginUser
from meridian_backend.schemas.register_user import RegisterUser, UserResponse
from meridian_backend.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: RegisterUser, service: Annotated[AuthService, Depends(get_auth_service)]
) -> UserResponse:
    user = await service.register(name=payload.name, email=payload.email, password=payload.password)
    return to_user_response(user)


@router.post("/login", response_model=UserResponse)
async def login_user(
    payload: LoginUser, service: Annotated[AuthService, Depends(get_auth_service)]
) -> UserResponse:
    user = await service.authenticate(email=payload.email, password=payload.password)
    return to_user_response(user)
