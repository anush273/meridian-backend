from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from meridian_backend.db.base import Base

if TYPE_CHECKING:
    from meridian_backend.db.models.order import OrderModel


class CustomerModel(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    email: Mapped[str] = mapped_column(String(320), nullable=False)

    orders: Mapped[list["OrderModel"]] = relationship(back_populates="customer")
