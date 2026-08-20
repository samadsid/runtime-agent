from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import (
    ChannelName,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    OnlinePaymentReady,
    PaymentMethod,
    StaleCheckout,
    StockUnavailable,
)
from commerce.repositories import DeliveryLocationNotServiceableError
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
    def __init__(
        self, service: PaymentService, require_whatsapp_location: bool = False
    ) -> None:
        self._service = service
        self._require_whatsapp_location = require_whatsapp_location

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
                            text="Online payment cannot start until the exact delivery location is serviceable.",
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
            or checkout.payment_method != PaymentMethod.ONLINE
            or None
            in (
                checkout.source_cart_id,
                checkout.source_cart_version,
                checkout.customer_name,
                checkout.phone_number,
                checkout.delivery_address,
            )
            or (
                self._require_whatsapp_location
                and input.context.channel is ChannelName.WHATSAPP
                and checkout.delivery_location is None
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
        try:
            result = await self._service.start_online_payment(
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
            stale = checkout.model_copy(
                update={
                    "stage": CheckoutStage.COLLECTING_DETAILS,
                    "delivery_address": None,
                    "delivery_location": None,
                    "payment_method": None,
                }
            )
            return CapabilityOutput(
                session=input.session.model_copy(update={"checkout": stale}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="saved-location-no-longer-serviceable",
                            text="The reviewed location is no longer serviceable. Payment was not started and the cart was preserved.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="share-another-delivery-location",
                        question="Please share another delivery location.",
                    ),
                ),
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
            session=session,
            outcome=payment_outcome(result.attempt, result.order.public_order_number),
        )
