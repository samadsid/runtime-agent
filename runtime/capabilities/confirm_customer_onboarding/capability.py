from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession, CustomerOnboardingState, OnboardingStage
from commerce.repositories import (
    SavedDeliveryPersistenceError,
    SavedDeliveryProfileConflictError,
)
from commerce.services import SavedDeliveryDetailsService
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


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfirmCustomerOnboardingCapability(Capability[CommerceSession]):
    def __init__(self, service: SavedDeliveryDetailsService) -> None:
        self._service = service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.CONFIRM_CUSTOMER_ONBOARDING,
            description="Persists the exact reviewed onboarding proposal after explicit confirmation; takes no arguments.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        state = input.session.customer_onboarding
        try:
            NoArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid(input.session)
        if state.stage is not OnboardingStage.REVIEWING_DETAILS or not all(
            (
                state.pending_customer_name,
                state.pending_phone_number,
                state.pending_delivery_address,
            )
        ):
            return self._invalid(input.session)
        customer_name = state.pending_customer_name
        phone_number = state.pending_phone_number
        delivery_address = state.pending_delivery_address
        assert customer_name is not None
        assert phone_number is not None
        assert delivery_address is not None
        try:
            await self._service.complete_onboarding(
                input.context.tenant_id,
                input.context.channel,
                input.context.channel_customer_id,
                customer_name,
                phone_number,
                delivery_address,
                datetime.now(timezone.utc),
                input.context.request_id,
            )
        except SavedDeliveryProfileConflictError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.CONFLICT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="customer-profile-changed",
                            text="The saved profile changed before confirmation, so the onboarding proposal was not written.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="review-saved-details",
                        question="Would you like to review the current saved details?",
                    ),
                ),
            )
        except SavedDeliveryPersistenceError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="customer-profile-temporarily-unavailable",
                            text="The profile could not be saved temporarily; the reviewed proposal remains available for retry.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="retry-customer-onboarding",
                        question="Would you like to try saving it again?",
                    ),
                ),
            )
        cleared = CustomerOnboardingState(stage=OnboardingStage.COMPLETED)
        return CapabilityOutput(
            session=input.session.model_copy(
                update={"customer_onboarding": cleared, "recent_saved_addresses": ()}
            ),
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="customer-profile-saved",
                        text="Your delivery details were saved for future orders. The phone number remains unverified.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="continue-shopping-after-onboarding",
                    question="What would you like to order?",
                ),
            ),
        )

    @staticmethod
    def _invalid(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="no-reviewed-customer-profile",
                        text="There is no complete reviewed customer profile to save.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="review-customer-profile",
                    question="Would you like to review your onboarding details first?",
                ),
            ),
        )
