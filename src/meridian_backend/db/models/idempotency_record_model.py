from datetime import UTC, datetime
from uuid import UUID,uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from meridian_backend.db.base import Base


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
