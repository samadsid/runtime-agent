from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    PaymentAttempt,
    PaymentAttemptStatus,
    PaymentMethod,
)
from commerce.payments import PaymentProviderInvalidResponseError
from infrastructure.payments import FakePaymentProvider
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.payment_support import payment_outcome
from runtime.capabilities.select_payment_method import SelectPaymentMethodCapability


def ready_checkout() -> CheckoutState:
    return CheckoutState(
        stage=CheckoutStage.READY_TO_CONFIRM,
        source_cart_id=uuid4(),
        source_cart_version=3,
        customer_name="Samad",
        phone_number="123",
        delivery_address="Market Road",
        payment_method=None,
    )


@pytest.mark.asyncio
async def test_payment_method_selection_is_closed_and_explicit() -> None:
    capability = SelectPaymentMethodCapability()
    session = CommerceSession(checkout=ready_checkout())

    selected = await capability.execute(
        CapabilityInput(
            data={"payment_method": "ONLINE"},
            session=session,
            context=ExecutionContext(tenant_id=uuid4(), conversation_id=uuid4()),
        )
    )

    assert selected.session.checkout.payment_method == PaymentMethod.ONLINE
    assert selected.outcome.fragments[0].id == "payment-method-selected"


@pytest.mark.asyncio
async def test_fake_webhook_verifies_exact_raw_bytes() -> None:
    secret = "test-webhook-secret"
    provider = FakePaymentProvider(None, "http://localhost:8000", secret)  # type: ignore[arg-type]
    payload = {
        "event_id": "evt_1",
        "payment_id": "fake_1",
        "status": "SUCCEEDED",
        "amount": "25.50",
        "currency": "INR",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()

    event = await provider.verify_and_parse_webhook(raw, signature)
    assert event.amount == Decimal("25.50")

    with pytest.raises(PaymentProviderInvalidResponseError):
        await provider.verify_and_parse_webhook(raw + b" ", signature)


def test_pending_payment_outcome_never_claims_success() -> None:
    now = datetime.now(timezone.utc)
    attempt = PaymentAttempt(
        id=uuid4(),
        tenant_id=UUID(int=0),
        order_id=uuid4(),
        provider="fake",
        provider_payment_id="fake_1",
        idempotency_key="key",
        amount=Decimal(100),
        currency="INR",
        status=PaymentAttemptStatus.PENDING,
        checkout_url="http://localhost:8000/dev/payments/fake_1",
        expires_at=now + timedelta(minutes=15),
        created_at=now,
        updated_at=now,
    )

    outcome = payment_outcome(attempt)

    assert outcome.fragments[0].id == "online-payment-ready"
    assert "succeeded" not in outcome.fragments[0].text.lower()
