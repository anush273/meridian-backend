import asyncio
from uuid import UUID


class ShippingService:
    async def prepare(self, order_id: UUID) -> str:
        await asyncio.sleep(1.5)
        return "shipping_prepared"
