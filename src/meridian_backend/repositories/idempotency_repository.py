from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from meridian_backend.db.models.idempotency_record_model import IdempotencyRecordModel


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_key(
        self, key: UUID, user_id: UUID, operation: str
    ) -> IdempotencyRecordModel | None:
        return await self.session.get(
            IdempotencyRecordModel,
            {"key": key, "user_id": user_id, "operation": operation},
        )

    async def add(self, record: IdempotencyRecordModel) -> None:
        self.session.add(record)
        await self.session.flush()
