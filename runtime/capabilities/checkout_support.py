from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

from commerce.models import CartItem, CheckoutState
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def next_missing_detail(checkout: CheckoutState) -> tuple[str, str] | None:
    if checkout.customer_name is None:
        return "customer-name", "What name should I use for this order?"
    if checkout.phone_number is None:
        return "phone-number", "What phone number should I use for delivery?"
    if checkout.delivery_address is None:
        return "delivery-address", "What is the complete delivery address?"
    return None


def missing_detail_outcome(checkout: CheckoutState) -> GeneratedExecutionOutcome:
    missing = next_missing_detail(checkout)
    if missing is None:
        raise ValueError("Checkout has no missing delivery detail.")
    field_id, question = missing
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=(
            ApprovedResponseFragment(
                id=f"missing-{field_id}",
                text="I need one more delivery detail to continue checkout.",
            ),
        ),
        follow_up=FollowUpRequest(id=f"request-{field_id}", question=question),
    )


def all_delivery_details_outcome() -> GeneratedExecutionOutcome:
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=(
            ApprovedResponseFragment(
                id="delivery-details-required",
                text="I need the delivery details to continue checkout.",
            ),
        ),
        follow_up=FollowUpRequest(
            id="request-delivery-details",
            question=(
                "What are your name, phone number, and complete delivery address?"
            ),
        ),
    )


def confirmation_review_outcome(
    checkout: CheckoutState,
    cart_items: tuple[CartItem, ...] = (),
    *,
    corrected: bool = False,
) -> GeneratedExecutionOutcome:
    if (
        checkout.customer_name is None
        or checkout.phone_number is None
        or checkout.delivery_address is None
    ):
        raise ValueError("Complete delivery details are required for review.")
    fragments: list[ApprovedResponseFragment] = []
    protected_values: list[str] = []
    if corrected:
        fragments.append(
            ApprovedResponseFragment(
                id="delivery-details-corrected",
                text="The corrected delivery details are ready for review.",
            )
        )
    if cart_items:
        fragments.append(
            ApprovedResponseFragment(
                id="corrected-checkout-cart-heading",
                text="Checkout cart review:",
            )
        )
        for ordinal, item in enumerate(cart_items, start=1):
            fragments.append(
                ApprovedResponseFragment(
                    id=f"corrected-checkout-item-{ordinal}",
                    text=(
                        f"{ordinal}. {item.product.name} — "
                        f"{format(item.quantity, 'f')} {item.product.unit} at "
                        f"₹{item.product.price}/{item.product.unit}"
                    ),
                    kind=ResponseFragmentKind.ITEM,
                )
            )
            protected_values.extend(
                (
                    str(ordinal),
                    item.product.name,
                    format(item.quantity, "f"),
                    item.product.unit,
                    f"₹{item.product.price}",
                )
            )
    fragments.extend(
        (
            ApprovedResponseFragment(
                id="delivery-name", text=f"Name: {checkout.customer_name}"
            ),
            ApprovedResponseFragment(
                id="delivery-phone", text=f"Phone: {checkout.phone_number}"
            ),
            ApprovedResponseFragment(
                id="delivery-address", text=f"Address: {checkout.delivery_address}"
            ),
            ApprovedResponseFragment(
                id="payment-method", text="Payment: CASH_ON_DELIVERY"
            ),
        )
    )
    protected_values.extend(
        (
            checkout.customer_name,
            checkout.phone_number,
            checkout.delivery_address,
            "CASH_ON_DELIVERY",
        )
    )
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=tuple(fragments),
        follow_up=FollowUpRequest(
            id="confirm-corrected-order" if corrected else "confirm-order",
            question="Please explicitly confirm that you want to place this order.",
        ),
        protected_values=tuple(protected_values),
    )
