from dataclasses import dataclass
from uuid import UUID
from enum import StrEnum

class UserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"



@dataclass
class User:
    id: UUID
    name: str
    email:str
    password_hash: str
    role: UserRole
    customer_id: UUID | None
    is_active: bool = True