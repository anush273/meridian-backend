from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from meridian_backend.api.dependencies import get_db_session
from meridian_backend.db.base import Base
from meridian_backend.db.models import CustomerModel
from meridian_backend.main import lifespan
from meridian_backend.models.product import Product
from meridian_backend.repositories.customer_repository import CustomerRepository
from meridian_backend.repositories.order_repository import OrderRepository
from meridian_backend.repositories.product_repository import ProductRepository
from meridian_backend.services.order_service import OrderService


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_session_context_exits_on_success_or_failure(fails: bool) -> None:
    app = FastAPI()
    session = AsyncMock(spec=AsyncSession)
    context = AsyncMock()
    context.__aenter__.return_value = session
    context.__aexit__.return_value = False
    factory = MagicMock(return_value=context)
    app.state.session_factory = factory
    request = Request({"type": "http", "app": app})
    dependency = get_db_session(request)

    assert await anext(dependency) is session
    if fails:
        with pytest.raises(RuntimeError, match="Request failed"):
            await dependency.athrow(RuntimeError("Request failed"))
    else:
        with pytest.raises(StopAsyncIteration):
            await anext(dependency)

    factory.assert_called_once_with()
    context.__aexit__.assert_awaited_once()
    session.begin.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_lifespan_disposes_engine(monkeypatch: pytest.MonkeyPatch, fails: bool) -> None:
    engine = MagicMock()
    engine.dispose = AsyncMock()
    factory = MagicMock()
    monkeypatch.setattr("meridian_backend.main.create_engine", lambda url: engine)
    monkeypatch.setattr("meridian_backend.main.create_session_factory", lambda eng: factory)
    app = FastAPI()

    async def run() -> None:
        async with lifespan(app):
            assert app.state.session_factory is factory
            if fails:
                raise RuntimeError("App failed")

    if fails:
        with pytest.raises(RuntimeError, match="App failed"):
            await run()
    else:
        await run()

    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_create_order_commits_or_rolls_back(tmp_path, customer, fails: bool) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'transactions.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine)
        product = Product(id=uuid4(), name="Book", price=Decimal("12.34"))
        async with factory() as session, session.begin():
            session.add(CustomerModel(id=customer.id, name=customer.name, email=customer.email))
            await ProductRepository(session).add(product)

        async with factory() as session:
            repository = OrderRepository(session)
            service = OrderService(
                repository, CustomerRepository(session), ProductRepository(session), session
            )
            if fails:
                original_add = repository.add

                async def fail_after_flush(order):
                    await original_add(order)
                    raise RuntimeError("Write failed")

                repository.add = fail_after_flush
                with pytest.raises(RuntimeError, match="Write failed"):
                    await service.create_order(customer.id, [(product.id, 2)])
            else:
                order = await service.create_order(customer.id, [(product.id, 2)])
            assert not session.in_transaction()

            async with factory() as verification_session:
                saved = await OrderRepository(verification_session).list_orders()
                assert saved == ([] if fails else [order])
    finally:
        await engine.dispose()
