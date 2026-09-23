from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from meridian_backend.core.config import Settings, get_settings
from meridian_backend.repositories.order_repository import OrderRepository
from meridian_backend.services.order_service import OrderService

SettingService = Annotated[Settings, Depends(get_settings)]


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide a session; the repository commits successful writes."""
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


def get_order_repository(session: DbSessionDep) -> OrderRepository:
    return OrderRepository(session)


OrderRepositoryDep = Annotated[OrderRepository, Depends(get_order_repository)]


def get_order_service(repository: OrderRepositoryDep) -> OrderService:
    return OrderService(repository)
