from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meridian_backend.core.config import Settings, get_settings
from meridian_backend.repositories.customer_repository import CustomerRepository
from meridian_backend.repositories.order_repository import OrderRepository
from meridian_backend.repositories.product_repository import ProductRepository
from meridian_backend.repositories.user_repository import UserRepository
from meridian_backend.services.auth_service import AuthService
from meridian_backend.services.order_service import OrderService

SettingService = Annotated[Settings, Depends(get_settings)]


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
    user_repository: Annotated[UserRepository, Depends(get_user_repository)], session: DbSessionDep
) -> AuthService:
    return AuthService(user_repository, session)
