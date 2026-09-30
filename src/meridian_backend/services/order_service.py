from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.core.exceptions import (
    CustomerNotFoundError,
    OrderNotFoundError,
    ProductNotFoundError,
    PermissionDeniedError
)
from meridian_backend.models.order import Order, OrderItem
from meridian_backend.repositories.customer_repository import CustomerRepository
from meridian_backend.repositories.order_repository import OrderRepository
from meridian_backend.repositories.product_repository import ProductRepository
from meridian_backend.models.user import User, UserRole
from meridian_backend.repositories.idempotency_repository import IdempotencyRepository



class OrderService:
    def __init__(
        self,
        order_repository: OrderRepository,
        customer_repository: CustomerRepository,
        product_repository: ProductRepository,
        session: AsyncSession,
        idempotency_repository: IdempotencyRepository
    ) -> None:
        self.session = session
        self.order_repository = order_repository
        self.customer_repository = customer_repository
        self.product_repository = product_repository
        self.idempotency_respository = idempotency_repository

    async def list_orders(self) -> list[Order]:
        return await self.order_repository.list_orders()

    async def create_order(
        self,
        *,
        actor:User,
        customer_id: UUID,
        items: list[tuple[UUID, int]],
        idempotency_key: str
    ) -> Order:
        async with self.session.begin():
            order_id = uuid4()
            claimed = await self.idempotency_respository.try_claim(
                key=idempotency_key,
                user_id=actor.id,
                operation="CREATE_ORDER",
                resource_id=order_id,
            )
            if not claimed:
                existing_order_id = await self.idempotency_respository.get_resource_id(
                    key=idempotency_key, user_id=actor.id, operation="CREATE_ORDER"
                )
                if existing_order_id is None:
                    raise RuntimeError("Idempotency claim exists but its record is missing")
                existing_order = await self.order_repository.get_by_id(existing_order_id)
                if existing_order is None:
                    raise RuntimeError("Idempotency record references missing order")
                return existing_order
            customer = await self.customer_repository.get_by_id(customer_id)
            if customer is None:
                raise CustomerNotFoundError(customer_id)
            products_by_id = await self.product_repository.get_products(
                [product_id for product_id, _ in items]
            )
            order_items: list[OrderItem] = []
            for product_id, quantity in items:
                product = products_by_id.get(product_id)
                if product is None:
                    raise ProductNotFoundError(product_id)
                order_items.append(OrderItem(product=product, quantity=quantity))
            order = Order(id=order_id, customer=customer, items=order_items)
            await self.order_repository.add(order)
        return order

    async def get_paid_orders(self) -> list[Order]:
        return [order for order in await self.list_orders() if order.status == "PAID"]

    async def calculate_revenue(self) -> Decimal:
        return sum((order.total() for order in await self.get_paid_orders()), Decimal("0"))

    async def get_orders_by_customer(
        self,
        customer_id: UUID,
    ) -> list[Order]:
        return [order for order in await self.list_orders() if order.customer.id == customer_id]

    async def get_highest_order(self) -> Order:
        return max(await self.list_orders(), key=lambda order: order.total())

    async def get_order_by_id(self, order_id: UUID, actor: User) -> Order:
        order = await self.order_repository.get_by_id(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        if actor.role == UserRole.ADMIN:
            return order
        if actor.customer_id != order.customer.id:
            raise PermissionDeniedError()
        return order
