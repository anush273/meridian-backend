from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from meridian_backend.db.mappers import (
    customer_model_to_domain,
    order_model_to_domain,
    product_model_to_domain,
)
from meridian_backend.db.models import CustomerModel, OrderItemModel, OrderModel, ProductModel
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order
from meridian_backend.models.product import Product


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _order_query():
        return select(OrderModel).options(
            selectinload(OrderModel.customer),
            selectinload(OrderModel.items).selectinload(OrderItemModel.product),
        )

    async def list_orders(self) -> list[Order]:
        result = await self.session.scalars(
            self._order_query().order_by(OrderModel.created_at, OrderModel.id)
        )
        return [order_model_to_domain(model) for model in result]

    async def get_by_id(self, order_id: UUID) -> Order | None:
        model = await self.session.scalar(self._order_query().where(OrderModel.id == order_id))
        return order_model_to_domain(model) if model is not None else None

    async def get_customer(self, customer_id: UUID) -> Customer | None:
        model = await self.session.get(CustomerModel, customer_id)
        if model is None:
            return None
        return customer_model_to_domain(model)

    async def get_products(self, product_ids: list[UUID]) -> dict[UUID, Product]:
        models = await self.session.scalars(
            select(ProductModel).where(ProductModel.id.in_(product_ids))
        )
        return {model.id: product_model_to_domain(model) for model in models}

    async def add(self, order: Order) -> None:
        model = OrderModel(
            id=order.id,
            customer_id=order.customer.id,
            status=order.status,
            created_at=order.created_at,
            items=[
                OrderItemModel(product_id=item.product.id, quantity=item.quantity)
                for item in order.items
            ],
        )
        try:
            self.session.add(model)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
