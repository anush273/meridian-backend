import asyncio
import logging
from decimal import Decimal
from uuid import UUID

from meridian_backend.core.exceptions import PaymentTimeoutError


logger = logging.getLogger(__name__)


async def charge_payment_provider(
    order_id: UUID,
    amount: Decimal,
    simulate_timeout: bool = False,
) -> str:
    if simulate_timeout:
        raise TimeoutError("Payment provider timed out")
    await asyncio.sleep(1.5)
    return "payment_approved"


class PaymentService:
    async def charge(
        self,
        order_id: UUID,
        amount: Decimal,
        simulate_timeout: bool = False,
    ) -> str:
        logger.info("payment_started", extra={"order_id": str(order_id), "amount": str(amount)})
        try:
            logger.info("payment_succeeded", extra={"order_id": order_id, "amount": amount})
            return await charge_payment_provider(order_id, amount, simulate_timeout)

        except TimeoutError as exc:
            logger.exception(
                "payment_timeout",
                extra={
                    "order_id": str(order_id),
                    "amount": str(amount),
                    "payment_provider": "simulated_provider",
                },
            )
            raise PaymentTimeoutError(
                order_id=order_id,
                payment_provider="simulated_provider",
            ) from exc
