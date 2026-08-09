from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CheckoutStage, CheckoutState, CommerceSession
from commerce.repositories import CartNotAvailableForCheckoutError
from commerce.services import OrderService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class ConfirmOrderArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class ConfirmOrderCapability(Capability[CommerceSession]):
    def __init__(self, service: OrderService) -> None:
        self._service = service

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
            checkout.stage != CheckoutStage.READY_TO_CONFIRM
            or checkout.source_cart_id is None
            or checkout.customer_name is None
            or checkout.phone_number is None
            or checkout.delivery_address is None
        ):
            return self._not_ready(input.session)

        try:
            order = await self._service.create_confirmed_order_from_cart(
                conversation_id=input.context.conversation_id,
                cart_id=checkout.source_cart_id,
                customer_name=checkout.customer_name,
                phone_number=checkout.phone_number,
                delivery_address=checkout.delivery_address,
            )
        except CartNotAvailableForCheckoutError:
            session = input.session.model_copy(
                update={"cart_items": (), "checkout": CheckoutState()}
            )
            return CapabilityOutput(
                session=session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.NOT_FOUND,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-cart-unavailable",
                            text="The checkout cart is empty or no longer available.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="restart-shopping",
                        question="What product would you like to search for?",
                    ),
                ),
            )

        session = input.session.model_copy(
            update={"cart_items": (), "checkout": CheckoutState()}
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="order-confirmed",
                        text=(
                            f"Order {order.id} is {order.status.value}. "
                            "Payment method: CASH_ON_DELIVERY."
                        ),
                    ),
                ),
                protected_values=(
                    str(order.id),
                    order.status.value,
                    order.payment_method.value,
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
