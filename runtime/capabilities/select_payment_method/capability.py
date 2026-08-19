from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import (
    Cart,
    CartStatus,
    CheckoutStage,
    CommerceSession,
    PaymentMethod,
)
from commerce.services import ConfiguredPaymentMethodPolicy, PaymentMethodPolicy
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import (
    confirmation_review_outcome,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class SelectPaymentMethodArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_method: PaymentMethod


class SelectPaymentMethodCapability(Capability[CommerceSession]):
    def __init__(self, payment_policy: PaymentMethodPolicy | None = None) -> None:
        self._payment_policy = payment_policy or ConfiguredPaymentMethodPolicy(
            (PaymentMethod.CASH_ON_DELIVERY, PaymentMethod.ONLINE),
            online_operational=True,
        )

    @property
    def metadata(self):
        return CapabilityMetadata(
            name=CapabilityName.SELECT_PAYMENT_METHOD,
            description="Selects ONLINE or CASH_ON_DELIVERY only from explicit customer intent during a complete checkout review.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]):
        try:
            args = SelectPaymentMethodArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="payment-method-invalid",
                            text="Choose online payment or cash on delivery.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="select-payment-method",
                        question="Would you like to pay online or with cash on delivery?",
                    ),
                ),
            )
        checkout = input.session.checkout
        if checkout.stage != CheckoutStage.SELECTING_PAYMENT_METHOD:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-not-ready",
                            text="Checkout is not ready for payment selection.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="start-checkout",
                        question="Would you like to continue checkout?",
                    ),
                ),
            )
        if checkout.source_cart_id is None:
            return self._unavailable(input.session)
        cart = Cart(
            id=checkout.source_cart_id,
            tenant_id=input.context.tenant_id,
            conversation_id=input.context.conversation_id,
            status=CartStatus.ACTIVE,
            version=checkout.source_cart_version or 0,
            items=input.session.cart_items,
        )
        eligible = await self._payment_policy.eligible_methods(
            input.context.tenant_id, cart
        )
        if args.payment_method not in {item.method for item in eligible}:
            return self._unavailable(input.session)
        checkout = checkout.model_copy(
            update={
                "payment_method": args.payment_method,
                "stage": CheckoutStage.READY_TO_CONFIRM,
            }
        )
        session = input.session.model_copy(update={"checkout": checkout})
        outcome = confirmation_review_outcome(checkout, input.session.cart_items)
        return CapabilityOutput(session=session, outcome=outcome)

    @staticmethod
    def _unavailable(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        checkout = session.checkout.model_copy(
            update={
                "stage": CheckoutStage.SELECTING_PAYMENT_METHOD,
                "payment_method": None,
            }
        )
        return CapabilityOutput(
            session=session.model_copy(update={"checkout": checkout}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="payment-method-no-longer-available",
                        text="That payment method is not currently available.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="choose-another-payment-method",
                    question="Please choose one of the currently available payment methods.",
                ),
            ),
        )
