from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import (
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    OnlinePaymentReady,
    PaymentMethod,
    StaleCheckout,
    StockUnavailable,
)
from commerce.services import PaymentService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.payment_support import payment_outcome
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class StartOnlinePaymentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


class StartOnlinePaymentCapability(Capability[CommerceSession]):
    def __init__(self, service: PaymentService) -> None:
        self._service = service

    @property
    def metadata(self):
        return CapabilityMetadata(
            name=CapabilityName.START_ONLINE_PAYMENT,
            description="Starts online payment only after complete checkout, explicit ONLINE selection, and confirmed=true. Takes no provider-controlled values.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]):
        try:
            StartOnlinePaymentArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="explicit-confirmation-required",
                            text="Online payment was not started without explicit confirmation.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="confirm-online-payment",
                        question="Do you explicitly confirm starting online payment?",
                    ),
                ),
            )
        checkout = input.session.checkout
        if (
            checkout.stage != CheckoutStage.READY_TO_CONFIRM
            or checkout.payment_method != PaymentMethod.ONLINE
            or None
            in (
                checkout.source_cart_id,
                checkout.source_cart_version,
                checkout.customer_name,
                checkout.phone_number,
                checkout.delivery_address,
            )
        ):
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-not-ready",
                            text="Checkout is not ready for online payment.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="complete-checkout",
                        question="Would you like to complete checkout first?",
                    ),
                ),
            )
        result = await self._service.start_online_payment(
            tenant_id=input.context.tenant_id,
            conversation_id=input.context.conversation_id,
            cart_id=checkout.source_cart_id,
            expected_cart_version=checkout.source_cart_version,
            customer_name=checkout.customer_name,
            phone_number=checkout.phone_number,
            delivery_address=checkout.delivery_address,
        )
        if isinstance(result, StockUnavailable):
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="order-stock-unavailable",
                            text="Online payment was not started because current stock is insufficient.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="review-current-cart",
                        question="Would you like to review the current cart?",
                    ),
                ),
            )
        if isinstance(result, StaleCheckout):
            return CapabilityOutput(
                session=input.session.model_copy(update={"checkout": CheckoutState()}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-cart-changed",
                            text="The checkout cart changed or is no longer active.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="review-current-cart",
                        question="Would you like to review the current cart?",
                    ),
                ),
            )
        assert isinstance(result, OnlinePaymentReady)
        session = input.session.model_copy(
            update={
                "cart_items": (),
                "checkout": CheckoutState(),
                "pending_cart_clear": None,
                "pending_saved_profile_use": None,
            }
        )
        return CapabilityOutput(
            session=session, outcome=payment_outcome(result.attempt)
        )
