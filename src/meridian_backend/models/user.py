from dataclasses import dataclass
from uuid import UUID


@dataclass
class User:
    id: UUID
    name: str
    email:str
    password_hash: str
    role: str
    is_active: bool = True