from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession, DeliveryInputMode, OnboardingStage
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.onboarding_support import (
    next_required_outcome,
    with_resolved_stage,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UseTextAddressForOnboardingCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.USE_TEXT_ADDRESS_FOR_ONBOARDING,
            description="Explicitly switches active location-first onboarding to text-address fallback; takes no arguments.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            NoArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid(input.session)
        state = input.session.customer_onboarding
        if state.stage is not OnboardingStage.COLLECTING_LOCATION:
            return self._invalid(input.session)
        state = with_resolved_stage(
            state.model_copy(
                update={
                    "delivery_input_mode": DeliveryInputMode.TEXT_ADDRESS,
                    "pending_delivery_location": None,
                }
            )
        )
        outcome = next_required_outcome(state).model_copy(
            update={
                "fragments": (
                    ApprovedResponseFragment(
                        id="onboarding-text-address-selected",
                        text="Text-address fallback was selected; no delivery location was saved.",
                    ),
                )
            }
        )
        return CapabilityOutput(
            session=input.session.model_copy(update={"customer_onboarding": state}),
            outcome=outcome,
        )

    @staticmethod
    def _invalid(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="onboarding-text-address-fallback-unavailable",
                        text="Text-address fallback is not available at the current onboarding stage.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="continue-current-onboarding-stage",
                    question="Please continue with the requested onboarding detail.",
                ),
            ),
        )
