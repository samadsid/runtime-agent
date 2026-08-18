from commerce.models import CommerceSession, CustomerOnboardingState, OnboardingStage
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


class SkipCustomerOnboardingCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.SKIP_CUSTOMER_ONBOARDING,
            description="Skips profile onboarding for this conversation and clears pending profile details; takes no arguments.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        state = CustomerOnboardingState(stage=OnboardingStage.SKIPPED)
        return CapabilityOutput(
            session=input.session.model_copy(
                update={
                    "customer_onboarding": state,
                    "deferred_customer_intent": None,
                }
            ),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="customer-onboarding-skipped",
                        text="Profile saving was skipped for this conversation; delivery details will still be required before order confirmation.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="continue-as-guest", question="What would you like to shop for?"
                ),
            ),
        )
