from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError

from commerce.models import CommerceSession, CustomerLocationUse
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


class ChooseCustomerLocationUseArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    save_address: StrictBool


class ChooseCustomerLocationUseCapability(Capability[CommerceSession]):
    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CHOOSE_CUSTOMER_LOCATION_USE,
            description=(
                "Chooses whether the current serviceable post-onboarding location "
                "will be saved as a new non-default address or used temporarily."
            ),
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        pending = input.session.pending_customer_location
        try:
            arguments = ChooseCustomerLocationUseArguments.model_validate(input.data)
        except ValidationError:
            arguments = None
        if pending is None or arguments is None:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="customer-location-use-invalid",
                            text="No valid pending delivery location choice was found.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="choose-customer-location-use",
                        question="Should this location be saved as a new address or used only for the current order?",
                    ),
                ),
            )
        use = (
            CustomerLocationUse.SAVE_NEW_ADDRESS
            if arguments.save_address
            else CustomerLocationUse.TEMPORARY
        )
        pending = pending.model_copy(update={"use": use})
        return CapabilityOutput(
            session=input.session.model_copy(
                update={"pending_customer_location": pending}
            ),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="customer-location-use-selected",
                        text=(
                            "The location will be added as a new non-default saved address."
                            if arguments.save_address
                            else "The location will be used temporarily and will not change saved addresses."
                        ),
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="delivery-address-details-required",
                    question="Please share the flat or house number, floor, entrance, and a nearby landmark.",
                ),
            ),
        )
