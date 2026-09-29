from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, StringConstraints


class RegisterUser(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginUser(BaseModel):
    email: EmailStr
    password: str
