from uuid import UUID

class MeridianError(Exception):
    """Base exceptions for Meridian."""

class OrderError(MeridianError):
    """Base exceptions for order related failures"""

class PaymentError(MeridianError):
    """Base exceptions for payment related failures"""

class  OrderNotFoundError(OrderError):
    def __init__(self, order_id: UUID) -> None:
        super().__init__(f"Order {order_id} not found")

class InvalidOrderStateError(OrderError):
    def __init__(self, order_id: UUID,current_status: str, attempted_operation: str) -> None:
        self.order_id =order_id
        self.current_status = current_status
        self.attempted_operatioj = attempted_operation
        super().__init__(
            f"Cannot {attempted_operation} order {order_id}"
            f"while status is {current_status}"
        )


class PaymentTimeoutError(PaymentError):
    def __init__(self, order_id: UUID, payment_provider: str) -> None:
        self.order_id = order_id
        self.payment_provider = payment_provider
        super().__init__(
            f"Payment provicer {payment_provider} timed out"
            f"for order {order_id}"
        )