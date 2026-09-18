from dataclasses import dataclass

from uuid import UUID


@dataclass
class Product:
    id: UUID
    name: str
    price: float
    