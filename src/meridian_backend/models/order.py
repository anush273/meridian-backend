from dataclasses import dataclass,field

from .product import Product
from .customer import Customer


@dataclass
class OrderItem :
    product: Product
    quantity: int
    
    def subtotal(self) -> float:
        return self.product.price * self.quantity


@dataclass
class Order: 
    id: int
    customer: Customer
    status: str
    items: list[OrderItem] =  field(default_factory=list[OrderItem])

    def subtotal(self) -> float:
        return sum((item.subtotal() for item in self.items), 0.0)

    def tax(self, tax_rate: float = 0.18) -> float:
        return self.subtotal() * tax_rate
        

    def total(self, tax_rate: float = 0.18) -> float:
        return self.subtotal() + self.tax(tax_rate)
  


        