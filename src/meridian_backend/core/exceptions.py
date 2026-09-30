from uuid import UUID


class MeridianError(Exception):
    """Base exceptions for Meridian."""


class OrderError(MeridianError):
    """Base exceptions for order related failures"""


class PaymentError(MeridianError):
    """Base exceptions for payment related failures"""


class PermissionDeniedError(MeridianError):
    """Base exceptions for permission related failures"""


class OrderNotFoundError(OrderError):
    def __init__(self, order_id: UUID) -> None:
        self.order_id = order_id
        super().__init__(f"Order {order_id} not found")


class InvalidOrderStateError(OrderError):
    def __init__(self, order_id: UUID, current_status: str, attempted_operation: str) -> None:
        self.order_id = order_id
        self.current_status = current_status
        self.attempted_operatioj = attempted_operation
        super().__init__(
            f"Cannot {attempted_operation} order {order_id}while status is {current_status}"
        )


class PaymentTimeoutError(PaymentError):
    def __init__(self, order_id: UUID, payment_provider: str) -> None:
        self.order_id = order_id
        self.payment_provider = payment_provider
        super().__init__(f"Payment provicer {payment_provider} timed outfor order {order_id}")


class CustomerNotFoundError(OrderError):
    def __init__(self, customer_id: UUID) -> None:
        self.customer_id = customer_id
        super().__init__(f"Customer {customer_id} not found")


class ProductNotFoundError(OrderError):
    def __init__(self, product_id: UUID) -> None:
        self.product_id = product_id
        super().__init__(f"Product {product_id} not found")


class AuthError(MeridianError):
    """Base exception for authentication and registration failures."""


class InvalidCredentialsError(AuthError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class WrongPasswordError(InvalidCredentialsError):
    """Password verification failed; keep the public credentials message generic."""


class InactiveUserError(AuthError):
    def __init__(self) -> None:
        super().__init__("User account is inactive")


class UserAlreadyExistsError(AuthError):
    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"{email} already exists")


class UserDoesNotExist(AuthError):
    def __init__(self, email: str) -> None:
        super().__init__(f"User {email} does not exist")


class InvalidAccessTokenError(MeridianError):
    def __init__(self) -> None:
        super().__init__(f"Invalid access token")


