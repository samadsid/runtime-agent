from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession
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
        return CapabilityOutput(
            session=input.session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                follow_up=FollowUpRequest(
                    id="share-delivery-location",
                    question="Please tap the attachment icon, choose Location, and send the delivery destination.",
                ),
            ),
        )
