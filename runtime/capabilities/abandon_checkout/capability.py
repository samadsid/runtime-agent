from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CheckoutStage, CheckoutState, CommerceSession
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


class AbandonCheckoutArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AbandonCheckoutCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.ABANDON_CHECKOUT,
            description=(
                "Stops an in-progress checkout while preserving the persisted cart."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            AbandonCheckoutArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="invalid-checkout-abandonment",
                            text="Checkout abandonment does not accept arguments.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="retry-checkout-abandonment",
                        question="Would you like to stop the current checkout?",
                    ),
                ),
            )

        if input.session.checkout.stage == CheckoutStage.NONE:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="checkout-not-active",
                            text="There is no active checkout to stop; your cart is unchanged.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="start-checkout",
                        question="Would you like to start checkout?",
                    ),
                ),
            )

        return CapabilityOutput(
            session=input.session.model_copy(update={"checkout": CheckoutState()}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="checkout-abandoned",
                        text="Checkout was stopped and your cart was kept unchanged.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="continue-shopping",
                    question="Would you like to continue shopping?",
                ),
            ),
        )
