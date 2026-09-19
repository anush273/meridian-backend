from typing import TypedDict
import asyncio


class OrderItem(TypedDict):
    name:str
    price: int
    quantity: int

class RawOrder(TypedDict): 
    id: int
    customer_name: str
    items: list[OrderItem]
    status: str

class ProcessOrder(RawOrder):
    subtotal: int
    tax: float
    total: float


raw_orders: list[RawOrder] = [
    {
        "id": 101,
        "customer_name": "  anush  ",
        "items": [
            {"name": "keyboard", "price": 3000, "quantity": 1},
            {"name": "mouse", "price": 1000, "quantity": 2},
        ],
        "status": "paid",
    },
    {
        "id": 102,
        "customer_name": "PRIYA",
        "items": [
            {"name": "monitor", "price": 15000, "quantity": 1},
        ],
        "status": "pending",
    },
]


def validate_order(order: RawOrder) -> bool:
    required_fields = {"id", "customer_name", "items", "status"}
    if not required_fields.issubset(order):
        return False
    if order["id"] <=0 or not order["customer_name"].strip():
        return False
    if not order["items"]:
        return False
    if order["status"].strip().lower() not in {"pending", "failed", "paid"}:
        return False
    
    return all(
        item["name"].strip() != ""
        and item["price"] >= 0 
        and item["quantity"] > 0
        for item in order["items"]
    )


def normalize_order(order: RawOrder):
    copied_order = order.copy()
    copied_order["customer_name"] = order["customer_name"].strip().title()
    copied_order["status"] = order["status"].strip().upper()
    return copied_order


def calculate_subtotal(order: RawOrder):
    items = order["items"]
    return sum(item["quantity"] * item["price"] for item in items)


def calculate_tax(subtotal:float, tax_rate: float=0.18) -> float:
    return subtotal * tax_rate
    


def process_order(order: RawOrder, tax_rate: float=0.18) -> ProcessOrder:
    if not validate_order(order):
        raise ValueError("Invalid order")
    normalized_order = normalize_order(order)
    subtotal = calculate_subtotal(normalized_order)
    tax = calculate_tax(subtotal, tax_rate)
    return ProcessOrder(
        **normalized_order,
        subtotal= subtotal,
        tax= tax,
        total= subtotal + tax
    )


def process_orders(
    orders: list[RawOrder],
    tax_rate: float = 0.18,
) -> list[ProcessOrder]:
    return [process_order(order, tax_rate) for order in orders]


def iter_processed_orders(
    orders: list[RawOrder],
    tax_rate: float = 0.18,
):
    for order in orders:
        yield process_order(order, tax_rate)


async def process_sequentially(
    order: Order,
    payment_service: PaymentService,
    inventory_service: InventoryService,
    shipping_service: ShippingService
):
    makePayment = await payment_service.charge(order.id,order.total())
    reserve = await inventory_service.reserve(order.id)
    ship = await shipping_service.ship(order.id)

    return makePayment, reserve, ship


async def process_concurrently(
    order: Order,
    payment_service: PaymentService,
    inventory_service: InventoryService,
    shipping_service: ShippingService
):
   payment, reserve,shipping = await asyncio.gather(
    payment_service.charge(order.id, order.total()),
    inventory_service.reserve(order.id),
    shipping_service.ship(order.id)
   )