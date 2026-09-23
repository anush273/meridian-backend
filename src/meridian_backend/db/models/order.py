from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_backend.db.base import Base

if TYPE_CHECKING:
    from meridian_backend.db.models.customer import CustomerModel
    from meridian_backend.db.models.order_item import OrderItemModel


class OrderModel(Base):
    __tablename__ = "orders"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    items: Mapped[list["OrderItemModel"]] = relationship(back_populates="order")
    customer: Mapped["CustomerModel"] = relationship(back_populates="orders")
