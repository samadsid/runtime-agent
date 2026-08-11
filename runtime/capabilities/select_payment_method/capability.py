from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CheckoutStage, CommerceSession, PaymentMethod
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import confirmation_review_outcome
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
        if checkout.stage != CheckoutStage.READY_TO_CONFIRM:
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
        checkout = checkout.model_copy(update={"payment_method": args.payment_method})
        session = input.session.model_copy(update={"checkout": checkout})
        outcome = confirmation_review_outcome(
            checkout, input.session.cart_items
        ).model_copy(
            update={
                "fragments": (
                    ApprovedResponseFragment(
                        id="payment-method-selected",
                        text=f"Payment method selected: {args.payment_method.value}.",
                    ),
                )
                + confirmation_review_outcome(
                    checkout, input.session.cart_items
                ).fragments
            }
        )
        return CapabilityOutput(session=session, outcome=outcome)
