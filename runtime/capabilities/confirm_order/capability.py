from __future__ import annotations

import logging
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import (
    Cart,
    CartStatus,
    ChannelName,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    OrderConfirmed,
    PaymentMethod,
    StaleCheckout,
    StockRecoveryAction,
    StockRecoveryOption,
    StockRecoveryState,
    StockShortage,
    StockUnavailable,
)
from commerce.repositories import (
    DeliveryLocationNotServiceableError,
    OrderConfirmationPersistenceError,
)
from commerce.services import OrderService, PaymentMethodPolicy
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    advance_to_payment,
    format_money,
    payment_method_label,
)
from runtime.contracts import (
    ApprovedOption,
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)

logger = logging.getLogger(__name__)


class ConfirmOrderArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class ConfirmOrderCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: OrderService,
        payment_policy: PaymentMethodPolicy | None = None,
        require_whatsapp_location: bool = False,
    ) -> None:
        self._service = service
        self._payment_policy = payment_policy
        self._require_whatsapp_location = require_whatsapp_location

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CONFIRM_ORDER,
            description=(
                "Creates the order only when checkout is ready and the customer "
                "explicitly confirms with confirmed=true."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            ConfirmOrderArguments.model_validate(input.data)
        except ValidationError:
            return self._confirmation_required(input.session)

        checkout = input.session.checkout
        if (
            self._require_whatsapp_location
            and input.context.channel is ChannelName.WHATSAPP
            and checkout.delivery_location is None
        ):
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={
                        "checkout": checkout.model_copy(
                            update={
                                "stage": CheckoutStage.COLLECTING_DETAILS,
                                "payment_method": None,
                            }
                        )
                    }
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.MISSING_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="delivery-location-requested",
                            text="The order needs an exact serviceable delivery location before confirmation.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="share-delivery-location",
                        question="Please send the delivery destination using WhatsApp Location.",
                    ),
                ),
            )
        if (
            checkout.stage != CheckoutStage.READY_TO_CONFIRM
            or checkout.source_cart_id is None
            or checkout.source_cart_version is None
            or checkout.customer_name is None
            or checkout.phone_number is None
            or checkout.delivery_address is None
            or checkout.payment_method != PaymentMethod.CASH_ON_DELIVERY
            or (
                self._require_whatsapp_location
                and input.context.channel is ChannelName.WHATSAPP
                and checkout.delivery_location is None
            )
        ):
            return self._not_ready(input.session)

        if self._payment_policy is not None:
            cart = Cart(
                id=checkout.source_cart_id,
                tenant_id=input.context.tenant_id,
                conversation_id=input.context.conversation_id,
                status=CartStatus.ACTIVE,
                version=checkout.source_cart_version,
                items=input.session.cart_items,
            )
            eligible = await self._payment_policy.eligible_methods(
                input.context.tenant_id, cart
            )
            if checkout.payment_method not in {item.method for item in eligible}:
                stale, outcome = await advance_to_payment(
                    checkout.model_copy(update={"payment_method": None}),
                    input.session.cart_items,
                    input.context.tenant_id,
                    self._payment_policy,
                )
                return CapabilityOutput(
                    session=input.session.model_copy(update={"checkout": stale}),
                    outcome=outcome.model_copy(
                        update={
                            "fragments": (
                                ApprovedResponseFragment(
                                    id="payment-method-no-longer-available",
                                    text="The selected payment method is no longer available.",
                                ),
                            )
                            + outcome.fragments
                        }
                    ),
                )

        try:
            result = await self._service.create_confirmed_order_from_cart(
                tenant_id=input.context.tenant_id,
                conversation_id=input.context.conversation_id,
                cart_id=checkout.source_cart_id,
                expected_cart_version=checkout.source_cart_version,
                customer_name=checkout.customer_name,
                phone_number=checkout.phone_number,
                delivery_address=checkout.delivery_address,
                delivery_location=checkout.delivery_location,
            )
        except DeliveryLocationNotServiceableError:
            checkout = checkout.model_copy(
                update={
                    "stage": CheckoutStage.COLLECTING_DETAILS,
                    "delivery_location": None,
                    "delivery_address": None,
                    "payment_method": None,
                }
            )
            return CapabilityOutput(
                session=input.session.model_copy(update={"checkout": checkout}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="saved-location-no-longer-serviceable",
                            text="The reviewed delivery location is no longer in the active delivery area. The order was not created and the cart was preserved.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="share-another-delivery-location",
                        question="Please share another delivery location.",
                    ),
                ),
            )
        except OrderConfirmationPersistenceError:
            logger.exception(
                "Order confirmation returned a persistence failure.",
                extra={"event": "order_confirmation_persistence_failure"},
            )
            return self._temporary_failure(input.session)
        if isinstance(result, StockUnavailable):
            return self._stock_unavailable(input.session, result)
        if isinstance(result, StaleCheckout):
            return self._stale_checkout(input.session, result)
        assert isinstance(result, OrderConfirmed)
        order = result.order
        total = sum(
            (item.unit_price * item.quantity for item in order.items),
            start=Decimal(0),
        )
        currencies = {item.currency for item in order.items}
        currency = next(iter(currencies), "INR")
        formatted_total = format_money(total, currency)
        session = input.session.model_copy(
            update={
                "cart_items": (),
                "checkout": CheckoutState(),
                "selected_product": None,
                "recent_product_results": (),
                "catalog_browse": None,
                "pending_cart_addition": None,
                "pending_saved_profile_use": None,
                "pending_cart_clear": None,
            }
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="order-confirmed",
                        text="✅ Order Confirmed",
                        kind=ResponseFragmentKind.SECTION,
                    ),
                    ApprovedResponseFragment(
                        id="public-order-number",
                        text=f"Order Number: {order.public_order_number}",
                        kind=ResponseFragmentKind.FIELD,
                    ),
                    ApprovedResponseFragment(
                        id="confirmed-order-payment",
                        text=f"Payment: {payment_method_label(order.payment_method)}",
                        kind=ResponseFragmentKind.FIELD,
                    ),
                    ApprovedResponseFragment(
                        id="confirmed-order-total",
                        text=f"Total: {formatted_total}",
                        kind=ResponseFragmentKind.TOTAL,
                    ),
                ),
                protected_values=(
                    order.public_order_number,
                    payment_method_label(order.payment_method),
                    formatted_total,
                ),
            ),
        )

    @staticmethod
    def _stock_unavailable(
        session: CommerceSession, result: StockUnavailable
    ) -> CapabilityOutput[CommerceSession]:
        options: list[StockRecoveryOption] = []
        for shortage_ordinal, shortage in enumerate(result.shortages, start=1):
            cart_ordinal = next(
                (
                    ordinal
                    for ordinal, item in enumerate(session.cart_items, start=1)
                    if item.product.id == shortage.product_id
                ),
                None,
            )
            if shortage.available_quantity > 0:
                options.append(
                    StockRecoveryOption(
                        ordinal=len(options) + 1,
                        action=StockRecoveryAction.ACCEPT_AVAILABLE,
                        shortage_ordinal=shortage_ordinal,
                    )
                )
            if cart_ordinal is not None:
                options.append(
                    StockRecoveryOption(
                        ordinal=len(options) + 1,
                        action=StockRecoveryAction.REMOVE_CART_ITEM,
                        shortage_ordinal=shortage_ordinal,
                        cart_ordinal=cart_ordinal,
                    )
                )
        options.extend(
            (
                StockRecoveryOption(
                    ordinal=len(options) + 1,
                    action=StockRecoveryAction.VIEW_CART,
                ),
                StockRecoveryOption(
                    ordinal=len(options) + 2,
                    action=StockRecoveryAction.ABANDON_CHECKOUT,
                ),
            )
        )
        recovery = StockRecoveryState(
            cart_id=result.cart_id,
            cart_version=result.cart_version,
            shortages=result.shortages,
            options=tuple(options),
        )
        checkout = session.checkout.model_copy(update={"stock_recovery": recovery})
        session = session.model_copy(update={"checkout": checkout})
        fragments = (
            ApprovedResponseFragment(
                id="order-stock-unavailable",
                text="The order was not confirmed because current stock is insufficient.",
            ),
            *tuple(
                ApprovedResponseFragment(
                    id=f"stock-shortage-{ordinal}",
                    text=(
                        f"{ordinal}. {shortage.product_name}: requested "
                        f"{format(shortage.requested_quantity, 'f')} {shortage.unit}; "
                        f"currently available "
                        f"{format(shortage.available_quantity, 'f')} {shortage.unit}."
                    ),
                    kind=ResponseFragmentKind.ITEM,
                )
                for ordinal, shortage in enumerate(result.shortages, start=1)
            ),
        )
        approved_options = tuple(
            ApprovedOption(
                id=f"stock-recovery-option-{option.ordinal}",
                label=ConfirmOrderCapability._recovery_option_label(
                    option, result.shortages
                ),
            )
            for option in options
        )
        protected_values = tuple(
            value
            for ordinal, shortage in enumerate(result.shortages, start=1)
            for value in (
                str(ordinal),
                shortage.product_name,
                format(shortage.requested_quantity, "f"),
                format(shortage.available_quantity, "f"),
                shortage.unit,
            )
        ) + tuple(str(option.ordinal) for option in options)
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.CONFLICT,
                fragments=fragments,
                follow_up=FollowUpRequest(
                    id="choose-stock-recovery",
                    question="How would you like to update or review checkout?",
                    options=approved_options,
                ),
                protected_values=protected_values,
            ),
        )

    @staticmethod
    def _recovery_option_label(
        option: StockRecoveryOption, shortages: tuple[StockShortage, ...]
    ) -> str:
        prefix = f"{option.ordinal}. "
        if option.action == StockRecoveryAction.VIEW_CART:
            return prefix + "Review the current cart"
        if option.action == StockRecoveryAction.ABANDON_CHECKOUT:
            return prefix + "Stop checkout"
        assert option.shortage_ordinal is not None
        shortage = shortages[option.shortage_ordinal - 1]
        if option.action == StockRecoveryAction.ACCEPT_AVAILABLE:
            return (
                prefix
                + f"Reduce {shortage.product_name} to "
                + f"{format(shortage.available_quantity, 'f')} {shortage.unit}"
            )
        assert option.cart_ordinal is not None
        return (
            prefix + f"Remove cart item {option.cart_ordinal}: {shortage.product_name}"
        )

    @staticmethod
    def _stale_checkout(
        session: CommerceSession, result: StaleCheckout
    ) -> CapabilityOutput[CommerceSession]:
        session = session.model_copy(
            update={
                "checkout": CheckoutState(),
                "pending_cart_clear": None,
                "pending_saved_profile_use": None,
            }
        )
        text = (
            "The cart changed after checkout was reviewed."
            if result.reason.value == "CART_CHANGED"
            else "The checkout cart is empty or no longer available."
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.CONFLICT,
                fragments=(
                    ApprovedResponseFragment(id="checkout-cart-changed", text=text),
                ),
                follow_up=FollowUpRequest(
                    id="review-current-cart",
                    question="Would you like to review the current cart?",
                ),
            ),
        )

    @staticmethod
    def _temporary_failure(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.FAILURE,
                fragments=(
                    ApprovedResponseFragment(
                        id="order-confirmation-temporarily-unavailable",
                        text="The order could not be confirmed safely right now.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="retry-order-confirmation",
                    question="Would you like to try confirming the order again?",
                ),
            ),
        )

    @staticmethod
    def _confirmation_required(
        session: CommerceSession,
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="explicit-confirmation-required",
                        text="The order has not been placed without explicit confirmation.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="confirm-order-explicitly",
                    question="Do you explicitly confirm that I should place this order?",
                ),
            ),
        )

    @staticmethod
    def _not_ready(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="checkout-not-ready",
                        text="Checkout is not ready for order confirmation.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="continue-checkout",
                    question="Would you like to continue checkout?",
                ),
            ),
        )
