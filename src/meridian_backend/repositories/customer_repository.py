from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.db.mappers import customer_model_to_domain
from meridian_backend.db.models.customer import CustomerModel
from meridian_backend.models.customer import Customer


class CustomerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, customer_id: UUID) -> Customer | None:
        model = await self.session.get(CustomerModel, customer_id)
        return customer_model_to_domain(model) if model is not None else None
