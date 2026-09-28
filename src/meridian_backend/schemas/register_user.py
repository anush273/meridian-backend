from pydantic import BaseModel, EmailStr
from uuid import UUID


class RegisterUser(BaseModel):
    name: str
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    role: str
    is_active: bool