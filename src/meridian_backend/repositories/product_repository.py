from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.db.mappers import product_model_to_domain
from meridian_backend.db.models import ProductModel
from meridian_backend.models.product import Product


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_products(self) -> list[Product]:
        models = await self.session.scalars(
            select(ProductModel).order_by(ProductModel.name, ProductModel.id)
        )
        return [product_model_to_domain(model) for model in models]

    async def get_by_id(self, product_id: UUID) -> Product | None:
        model = await self.session.get(ProductModel, product_id)
        return product_model_to_domain(model) if model is not None else None

    async def get_products(self, product_ids: list[UUID]) -> dict[UUID, Product]:
        if not product_ids:
            return {}
        models = await self.session.scalars(
            select(ProductModel).where(ProductModel.id.in_(product_ids))
        )
        return {model.id: product_model_to_domain(model) for model in models}

    async def add(self, product: Product) -> None:
        model = ProductModel(id=product.id, name=product.name, price=product.price)
        self.session.add(model)
        await self.session.flush()
