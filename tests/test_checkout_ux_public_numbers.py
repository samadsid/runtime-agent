from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import (
    Cart,
    CartItem,
    CartStatus,
    CheckoutStage,
    CheckoutState,
    PaymentMethod,
    Product,
)
from commerce.services import ConfiguredPaymentMethodPolicy
from runtime.capabilities.checkout_support import advance_to_payment
from runtime.responses import ResponseGenerator, ResponseLayout


def cart_items() -> tuple[CartItem, ...]:
    return (
        CartItem(
            product=Product(
                id=uuid4(),
                name="Chicken Breast",
                price=Decimal("320.00"),
                currency="INR",
                unit="kg",
            ),
            quantity=Decimal("2.5"),
        ),
    )


@pytest.mark.asyncio
async def test_cod_only_policy_auto_selects_and_builds_complete_review() -> None:
    tenant_id = uuid4()
    checkout = CheckoutState(
        stage=CheckoutStage.COLLECTING_DETAILS,
        source_cart_id=uuid4(),
        source_cart_version=2,
        customer_name="Samad",
        phone_number="9560717170",
        delivery_address="B-68 New Zafrabad",
    )
    policy = ConfiguredPaymentMethodPolicy(
        (PaymentMethod.CASH_ON_DELIVERY,), online_operational=False
    )

    ready, outcome = await advance_to_payment(
        checkout, cart_items(), tenant_id, policy
    )
    fallback = ResponseGenerator._render_approved_fallback(
        outcome, ResponseLayout.LIST
    )

    assert ready.stage is CheckoutStage.READY_TO_CONFIRM
    assert ready.payment_method is PaymentMethod.CASH_ON_DELIVERY
    assert "Cash on Delivery" in fallback
    assert "Phone: ******7170" in fallback
    assert "Total: ₹800" in fallback
    assert fallback.endswith("Cash on Delivery?")
    assert outcome.follow_up is not None
    assert outcome.follow_up.id == "confirm-order-placement"


@pytest.mark.asyncio
async def test_multiple_operational_methods_require_explicit_selection() -> None:
    tenant_id = uuid4()
    items = cart_items()
    policy = ConfiguredPaymentMethodPolicy(
        (PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.ONLINE),
        online_operational=True,
    )
    cart = Cart(
        id=uuid4(),
        tenant_id=tenant_id,
        conversation_id=uuid4(),
        status=CartStatus.ACTIVE,
        items=items,
    )
    eligible = await policy.eligible_methods(tenant_id, cart)
    checkout = CheckoutState(
        stage=CheckoutStage.COLLECTING_DETAILS,
        source_cart_id=cart.id,
        customer_name="Samad",
        phone_number="9560717170",
        delivery_address="Address",
    )

    selecting, outcome = await advance_to_payment(
        checkout, items, tenant_id, policy
    )

    assert selecting.stage is CheckoutStage.SELECTING_PAYMENT_METHOD
    assert selecting.payment_method is None
    assert tuple(method.method for method in eligible) == (
        PaymentMethod.CASH_ON_DELIVERY,
        PaymentMethod.ONLINE,
    )
    assert outcome.follow_up is not None
    assert tuple(option.label for option in outcome.follow_up.options) == (
        "1. Cash on Delivery",
        "2. Online Payment",
    )
