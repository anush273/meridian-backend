from typing import Annotated

from fastapi import APIRouter, Depends, status

from meridian_backend.api.dependencies import get_auth_service, CurrentUserDep, AdminUserDep
from meridian_backend.api.mappers import to_user_response
from meridian_backend.schemas.login_user import LoginUser
from meridian_backend.schemas.register_user import RegisterUser, UserResponse, TokenResponse
from meridian_backend.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: RegisterUser, service: Annotated[AuthService, Depends(get_auth_service)]
) -> UserResponse:
    user = await service.register(name=payload.name, email=payload.email, password=payload.password)
    return to_user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginUser, service: Annotated[AuthService, Depends(get_auth_service)]
) -> TokenResponse:
    token = await service.login(
        email=payload.email,
        password=payload.password
    )
    return TokenResponse(
        access_token=token
    )

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user:CurrentUserDep
) -> UserResponse:
    return to_user_response(current_user)


@router.get("/admin/check")
async def admin_check(current_user:AdminUserDep):
    return {"message": "admin access granted"}