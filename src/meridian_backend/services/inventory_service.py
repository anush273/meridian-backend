import asyncio
from uuid import UUID


class InventoryService:
    async def reserve(self, order_id: UUID) -> str:
        await asyncio.sleep(2)
        return "inventory_reserved"
