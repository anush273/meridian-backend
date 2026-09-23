from collections.abc import Callable

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session

from meridian_backend.db.base import Base
from meridian_backend.db.models import CustomerModel, OrderItemModel, OrderModel, ProductModel
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.models.product import Product


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    path = tmp_path / "orders.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(
        "meridian_backend.main.create_engine",
        lambda url: create_async_engine(f"sqlite+aiosqlite:///{path}"),
    )
    yield engine
    engine.dispose()


@pytest.fixture
def seed(database) -> Callable:
    def insert(customers: list[Customer], products: list[Product], orders: list[Order]) -> None:
        with Session(database) as session:
            for customer in customers:
                session.add(CustomerModel(id=customer.id, name=customer.name, email=customer.email))
            for product in products:
                session.add(ProductModel(id=product.id, name=product.name, price=product.price))
            session.flush()
            for order in orders:
                session.add(
                    OrderModel(
                        id=order.id,
                        customer_id=order.customer.id,
                        status=order.status,
                        created_at=order.created_at,
                        items=[
                            OrderItemModel(product_id=item.product.id, quantity=item.quantity)
                            for item in order.items
                        ],
                    )
                )
            session.commit()

    return insert
