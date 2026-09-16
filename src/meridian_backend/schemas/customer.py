from datetime import  datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CreateCustomer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None



class CustomerResponse(BaseModel):
    id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    created_at: datetime
    updated_at: datetime | None
   
