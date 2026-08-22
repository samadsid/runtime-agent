from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints

from commerce.models import (
    Cart,
    CartItem,
    CartStatus,
    CheckoutStage,
    CheckoutState,
    PaymentMethod,
)
from commerce.services import PaymentMethodPolicy
from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
    ResponseIcon,
    ResponseLayout,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def payment_method_label(payment_method: PaymentMethod) -> str:
    return {
        PaymentMethod.CASH_ON_DELIVERY: "Cash on Delivery",
        PaymentMethod.ONLINE: "Online Payment",
    }[payment_method]


def format_money(amount: Decimal, currency: str) -> str:
    value = format(amount, "f")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    symbol = "₹" if currency == "INR" else f"{currency} "
    return f"{symbol}{value}"


def mask_phone(phone: str) -> str:
    stripped = phone.strip()
    return "*" * max(0, len(stripped) - 4) + stripped[-4:]


async def advance_to_payment(
    checkout: CheckoutState,
    cart_items: tuple[CartItem, ...],
    tenant_id: UUID,
    policy: PaymentMethodPolicy,
    *,
    corrected: bool = False,
) -> tuple[CheckoutState, GeneratedExecutionOutcome]:
    if checkout.source_cart_id is None:
        raise ValueError("Checkout source cart is required.")
    cart = Cart(
        id=checkout.source_cart_id,
        tenant_id=tenant_id,
        conversation_id=UUID(int=0),
        status=CartStatus.ACTIVE,
        version=checkout.source_cart_version or 0,
        items=cart_items,
    )
    eligible = await policy.eligible_methods(tenant_id, cart)
    if not eligible:
        checkout = checkout.model_copy(
            update={
                "stage": CheckoutStage.SELECTING_PAYMENT_METHOD,
                "payment_method": None,
            }
        )
        return checkout, GeneratedExecutionOutcome(
            status=ExecutionStatus.FAILURE,
            fragments=(
                ApprovedResponseFragment(
                    id="payment-methods-unavailable",
                    text="No payment method is currently available for this cart.",
                ),
            ),
        )
    if len(eligible) == 1:
        selected = eligible[0]
        checkout = checkout.model_copy(
            update={
                "stage": CheckoutStage.READY_TO_CONFIRM,
                "payment_method": selected.method,
            }
        )
        return checkout, confirmation_review_outcome(
            checkout, cart_items, corrected=corrected, auto_selected=True
        )
    checkout = checkout.model_copy(
        update={
            "stage": CheckoutStage.SELECTING_PAYMENT_METHOD,
            "payment_method": None,
        }
    )
    options = tuple(
        ApprovedOption(id=f"payment-method-{index}", label=f"{index}. {method.customer_label}")
        for index, method in enumerate(eligible, start=1)
    )
    return checkout, GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=(
            ApprovedResponseFragment(
                id="available-payment-methods",
                text="Payment Method",
                kind=ResponseFragmentKind.SECTION,
            ),
        ),
        follow_up=FollowUpRequest(
            id="select-payment-method",
            question="Which payment method would you like to use?",
            options=options,
        ),
        protected_values=tuple(option.label for option in options),
        layout=ResponseLayout.SELECTABLE_LIST,
        heading_emoji=ResponseIcon.PAYMENT,
    )


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


def all_delivery_details_outcome(
    *, saved_addresses_available: bool = False
) -> GeneratedExecutionOutcome:
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
                "Would you like to view saved addresses, or provide your name, "
                "phone number, and complete delivery address?"
                if saved_addresses_available
                else "What are your name, phone number, and complete delivery address?"
            ),
        ),
    )


def confirmation_review_outcome(
    checkout: CheckoutState,
    cart_items: tuple[CartItem, ...] = (),
    *,
    corrected: bool = False,
    auto_selected: bool = False,
) -> GeneratedExecutionOutcome:
    if (
        checkout.customer_name is None
        or checkout.phone_number is None
        or checkout.delivery_address is None
    ):
        raise ValueError("Complete delivery details are required for review.")
    if checkout.payment_method is None:
        raise ValueError("A payment method is required for final review.")
    fragments: list[ApprovedResponseFragment] = []
    protected_values: list[str] = []
    if corrected:
        fragments.append(
            ApprovedResponseFragment(
                id="delivery-details-corrected",
                text="The corrected checkout details are ready for review.",
            )
        )
    fragments.append(
        ApprovedResponseFragment(
            id="checkout-final-review",
            text="Order Summary",
            kind=ResponseFragmentKind.SECTION,
        )
    )
    currencies = {item.product.currency for item in cart_items}
    if len(currencies) > 1:
        raise ValueError("Checkout review requires one currency.")
    currency = next(iter(currencies), "INR")
    total = Decimal(0)
    for ordinal, item in enumerate(cart_items, start=1):
        line_total = item.quantity * item.product.price
        total += line_total
        unit_price = format_money(item.product.price, currency)
        line_amount = format_money(line_total, currency)
        fragments.append(
            ApprovedResponseFragment(
                id=f"checkout-final-item-{ordinal}",
                text=(
                    f"{ordinal}. {item.product.name}\n"
                    f"{format(item.quantity, 'f')} {item.product.unit} × "
                    f"{unit_price}/{item.product.unit} = {line_amount}"
                ),
                kind=ResponseFragmentKind.ITEM,
            )
        )
        protected_values.extend(
            (
                str(ordinal), item.product.name, format(item.quantity, "f"),
                item.product.unit, unit_price, line_amount,
            )
        )
    formatted_total = format_money(total, currency)
    fragments.extend(
        (
            ApprovedResponseFragment(
                id="checkout-total",
                text=f"Total: {formatted_total}",
                kind=ResponseFragmentKind.TOTAL,
            ),
            ApprovedResponseFragment(
                id="checkout-delivery-heading",
                text="Delivery",
                kind=ResponseFragmentKind.SECTION,
            ),
            ApprovedResponseFragment(
                id="delivery-name", text=f"Name: {checkout.customer_name}",
                kind=ResponseFragmentKind.FIELD,
            ),
            ApprovedResponseFragment(
                id="delivery-phone", text=f"Phone: {mask_phone(checkout.phone_number)}",
                kind=ResponseFragmentKind.FIELD,
            ),
            ApprovedResponseFragment(
                id="delivery-address", text=f"Address: {checkout.delivery_address}",
                kind=ResponseFragmentKind.FIELD,
            ),
            ApprovedResponseFragment(
                id="cash-on-delivery-selected" if auto_selected else "payment-method-selected",
                text="Payment",
                kind=ResponseFragmentKind.SECTION,
            ),
            ApprovedResponseFragment(
                id="payment-method",
                text=payment_method_label(checkout.payment_method),
                kind=ResponseFragmentKind.FIELD,
            ),
        )
    )
    protected_values.extend(
        (
            checkout.customer_name,
            mask_phone(checkout.phone_number),
            checkout.delivery_address,
            formatted_total,
            payment_method_label(checkout.payment_method),
        )
    )
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.SUCCESS,
        fragments=tuple(fragments),
        follow_up=FollowUpRequest(
            id="confirm-order-placement",
            question=(
                f"Should I place this order with {payment_method_label(checkout.payment_method)}?"
            ),
        ),
        protected_values=tuple(protected_values),
        layout=ResponseLayout.SUMMARY,
        heading_emoji=ResponseIcon.REVIEW,
    )
