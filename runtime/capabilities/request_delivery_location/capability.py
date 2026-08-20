from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession, OnboardingStage
from runtime.capabilities import (
    Capability, CapabilityInput, CapabilityMetadata, CapabilityName, CapabilityOutput,
)
from runtime.contracts import ApprovedResponseFragment, ExecutionStatus, FollowUpRequest, GeneratedExecutionOutcome


class RequestDeliveryLocationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestDeliveryLocationCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.REQUEST_DELIVERY_LOCATION,
            description="Requests a delivery-destination location pin; takes no arguments.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]) -> CapabilityOutput[CommerceSession]:
        try:
            RequestDeliveryLocationArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(session=input.session, outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(ApprovedResponseFragment(id="location-message-invalid", text="The delivery-location request was invalid."),),
            ))
        onboarding = input.session.customer_onboarding
        if onboarding.stage in {OnboardingStage.NOT_STARTED, OnboardingStage.REVIEWING_DETAILS}:
            onboarding = onboarding.model_copy(update={"stage": OnboardingStage.COLLECTING_DETAILS})
        return CapabilityOutput(
            session=input.session.model_copy(update={"customer_onboarding": onboarding}),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(ApprovedResponseFragment(
                    id="delivery-location-requested",
                    text="Share the WhatsApp location attachment for the place where delivery is required. The pin is used to check delivery coverage; it is not saved until you confirm the final review.",
                ),),
                follow_up=FollowUpRequest(
                    id="share-delivery-location",
                    question="Tap the attachment icon, choose Location, and send the delivery destination, or say if location sharing is unavailable.",
                ),
            ),
        )
