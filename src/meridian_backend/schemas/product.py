from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    description: str | None = None


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    price: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    description: str | None = None


class ProductResponse(BaseModel):
    id: UUID
    name: str
    price: Decimal
    description: str | None
    created_at: datetime
    updatedAt: datetime | None = None
