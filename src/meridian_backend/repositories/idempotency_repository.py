from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from meridian_backend.db.models.idempotency_record_model import IdempotencyRecordModel


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_resource_id(
        self, key: str, user_id: UUID, operation: str
    ) -> UUID| None:
        statement = select(IdempotencyRecordModel.resource_id).where(IdempotencyRecordModel.key == key, IdempotencyRecordModel.user_id == user_id, IdempotencyRecordModel.operation == operation)
        return await self.session.scalar(statement)

    async def add(
        self,
        *,
        key: str,
        user_id: UUID,
        operation: str,
        resource_id: UUID,
    ) -> None:
        record = IdempotencyRecordModel(
            key=key,
            user_id=user_id,
            operation=operation,
            resource_id=resource_id,
        )

        self.session.add(record)
        await self.session.flush()

    async def try_claim(self, *, key: str, user_id: UUID, operation: str, resource_id: UUID) -> bool:
        statement = (
            insert(IdempotencyRecordModel).values(
                key = key,
                user_id = user_id,
                operation= operation,
                resource_id = resource_id
            ).on_conflict_do_nothing(
                constraint="uq_idempotency_user_operation_key"
            ).returning(IdempotencyRecordModel.id)
        )

        result = await self.session.scalar(statement)
        return result is not None