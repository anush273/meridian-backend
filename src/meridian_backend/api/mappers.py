from meridian_backend.models.order import Order
from meridian_backend.models.user import User
from meridian_backend.schemas.order import OrderResponse
from meridian_backend.schemas.register_user import UserResponse


def to_order_response(order: Order) -> OrderResponse:
    return OrderResponse.model_validate(
        {
            "id": order.id,
            "customer_id": order.customer.id,
            "items": [
                {
                    "product_id": item.product.id,
                    "quantity": item.quantity,
                    "price": item.product.price,
                    "subtotal": item.subtotal(),
                }
                for item in order.items
            ],
            "status": order.status,
            "subtotal": order.subtotal(),
            "tax": order.tax(),
            "total": order.total(),
            "createdAt": order.created_at,
        }
    )


def to_user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(
        {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
