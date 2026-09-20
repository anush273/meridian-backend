from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from meridian_backend.core.exceptions import PaymentTimeoutError
from meridian_backend.services.payment_service import PaymentService


@pytest.mark.asyncio
async def test_charge_returns_payment_approved(monkeypatch: pytest.MonkeyPatch) -> None:
    order_id = uuid4()
    amount = Decimal("100.00")
    provider = AsyncMock(return_value="payment_approved")
    monkeypatch.setattr(
        "meridian_backend.services.payment_service.charge_payment_provider", provider
    )

    result = await PaymentService().charge(order_id, amount)

    assert result == "payment_approved"
    provider.assert_awaited_once_with(order_id, amount, False)


@pytest.mark.asyncio
async def test_charge_preserves_provider_timeout_as_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = uuid4()
    amount = Decimal("100.00")
    timeout = TimeoutError("Provider timed out")
    provider = AsyncMock(side_effect=timeout)
    monkeypatch.setattr(
        "meridian_backend.services.payment_service.charge_payment_provider", provider
    )

    with pytest.raises(PaymentTimeoutError) as exc_info:
        await PaymentService().charge(order_id, amount)

    assert exc_info.value.__cause__ is timeout
    assert exc_info.value.order_id == order_id
    assert exc_info.value.payment_provider == "simulated_provider"
    provider.assert_awaited_once_with(order_id, amount, False)
