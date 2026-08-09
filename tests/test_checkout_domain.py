from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from commerce.models import CheckoutStage, CheckoutState, OrderItem


def test_checkout_state_is_immutable_and_defaults_to_none() -> None:
    checkout = CheckoutState()

    assert checkout.stage == CheckoutStage.NONE
    with pytest.raises(ValidationError):
        checkout.stage = CheckoutStage.REVIEWING_CART  # type: ignore[misc]


def test_order_item_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        OrderItem(
            id=uuid4(),
            order_id=uuid4(),
            product_id=uuid4(),
            product_name="Chicken",
            unit="kg",
            unit_price=Decimal(10),
            quantity=Decimal(0),
        )
