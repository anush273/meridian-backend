from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import (HTTPBearer,HTTPAuthorizationCredentials)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meridian_backend.core.config import Settings, get_settings
from meridian_backend.repositories.customer_repository import CustomerRepository
from meridian_backend.repositories.order_repository import OrderRepository
from meridian_backend.repositories.product_repository import ProductRepository
from meridian_backend.repositories.user_repository import UserRepository
from meridian_backend.services.auth_service import AuthService
from meridian_backend.services.order_service import OrderService
from meridian_backend.models.user import User, UserRole
from meridian_backend.core.security import decode_access_token
from meridian_backend.core.exceptions import InvalidAccessTokenError, InactiveUserError, PermissionDeniedError


SettingService = Annotated[Settings, Depends(get_settings)]

bearer_scheme = HTTPBearer()

async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a shared session; services own write transactions."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_order_repository(session: DbSessionDep) -> OrderRepository:
    return OrderRepository(session)


OrderRepositoryDep = Annotated[OrderRepository, Depends(get_order_repository)]


def get_customer_repository(session: DbSessionDep) -> CustomerRepository:
    return CustomerRepository(session)


CustomerRepositoryDep = Annotated[CustomerRepository, Depends(get_customer_repository)]


def get_product_repository(session: DbSessionDep) -> ProductRepository:
    return ProductRepository(session)


ProductRepositoryDep = Annotated[ProductRepository, Depends(get_product_repository)]


def get_order_service(
    repository: OrderRepositoryDep,
    customer_repository: CustomerRepositoryDep,
    product_repository: ProductRepositoryDep,
    session: DbSessionDep,
) -> OrderService:
    return OrderService(repository, customer_repository, product_repository, session)


def get_user_repository(session: DbSessionDep) -> UserRepository:
    return UserRepository(session)


def get_auth_service(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)], session: DbSessionDep, settings: SettingService
) -> AuthService:
    return AuthService(user_repository, session, settings)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


async def get_current_user(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)], user_repository: UserRepositoryDep, settings: SettingService) -> User:
    user_id = decode_access_token(credentials.credentials,settings)
    user = await user_repository.get_by_id(user_id)

    if user is None:
        raise InvalidAccessTokenError()
    
    if not user.is_active:
        raise InactiveUserError()
    
    return user

CurrentUserDep = Annotated[User, Depends(get_current_user)]

async def require_admin(current_user: CurrentUserDep) -> User:
    if current_user.role != UserRole.ADMIN:
        raise PermissionDeniedError()
    return current_user


AdminUserDep = Annotated[User, Depends(require_admin)]
