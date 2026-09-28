import asyncio
from decimal import Decimal

from meridian_backend.core.config import get_settings
from meridian_backend.db.models.customer import CustomerModel
from meridian_backend.db.models.product import ProductModel
from meridian_backend.db.session import (
    create_engine,
    create_session_factory,
)


async def main() -> None:
    settings = get_settings()

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        async with session.begin():
            customer = CustomerModel(
                name="Test Customer",
                email="test@example.com",
            )

            product_1 = ProductModel(
                name="Mechanical Keyboard",
                price=Decimal("4999.00"),
            )

            product_2 = ProductModel(
                name="Wireless Mouse",
                price=Decimal("1999.00"),
            )

            session.add_all([
                customer,
                product_1,
                product_2,
            ])

        print("Customer:", customer.id)
        print("Keyboard:", product_1.id)
        print("Mouse:", product_2.id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())