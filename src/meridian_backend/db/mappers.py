"""Convert database models with loaded relationships into domain objects."""

from datetime import UTC

from meridian_backend.db.models import CustomerModel, OrderItemModel, OrderModel, ProductModel
from meridian_backend.models.customer import Customer
from meridian_backend.models.order import Order, OrderItem
from meridian_backend.models.product import Product


def customer_model_to_domain(model: CustomerModel) -> Customer:
    return Customer(id=model.id, name=model.name, email=model.email)


def product_model_to_domain(model: ProductModel) -> Product:
    return Product(id=model.id, name=model.name, price=model.price)


def order_item_model_to_domain(model: OrderItemModel) -> OrderItem:
    return OrderItem(product=product_model_to_domain(model.product), quantity=model.quantity)


def order_model_to_domain(model: OrderModel) -> Order:
    return Order(
        id=model.id,
        customer=customer_model_to_domain(model.customer),
        status=model.status,
        created_at=(
            model.created_at.replace(tzinfo=UTC)
            if model.created_at.tzinfo is None
            else model.created_at
        ),
        items=[order_item_model_to_domain(item) for item in model.items],
    )
