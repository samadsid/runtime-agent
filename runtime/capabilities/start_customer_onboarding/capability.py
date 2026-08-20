from __future__ import annotations

from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerOnboardingState,
    DeliveryInputMode,
    OnboardingStage,
)
from commerce.repositories import SavedDeliveryPersistenceError
from commerce.services import SavedDeliveryDetailsService
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.onboarding_support import (
    next_required_outcome,
    review_outcome,
    with_resolved_stage,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class StartCustomerOnboardingCapability(Capability[CommerceSession]):
    def __init__(
        self,
        service: SavedDeliveryDetailsService,
        require_whatsapp_location: bool = False,
    ) -> None:
        self._service = service
        self._require_whatsapp_location = require_whatsapp_location

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.START_CUSTOMER_ONBOARDING,
            description="Offers first-visit profile onboarding using trusted channel identity; takes no arguments.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        context = input.context
        current = input.session.customer_onboarding
        if current.stage in {
            OnboardingStage.COLLECTING_IDENTITY,
            OnboardingStage.COLLECTING_LOCATION,
            OnboardingStage.COLLECTING_ADDRESS_DETAILS,
            OnboardingStage.REVIEWING_PROFILE,
        }:
            return CapabilityOutput(
                session=input.session,
                outcome=(
                    review_outcome(current)
                    if current.stage is OnboardingStage.REVIEWING_PROFILE
                    else next_required_outcome(current)
                ),
            )
        if context.channel_customer_id is None:
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={
                        "customer_onboarding": CustomerOnboardingState(
                            stage=OnboardingStage.NOT_REQUIRED
                        )
                    }
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="profile-memory-unavailable-for-guest",
                            text="Reusable profile memory is unavailable without a stable trusted channel identity; delivery details can still be supplied during checkout.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="continue-as-guest",
                        question="What would you like to shop for?",
                    ),
                ),
            )
        if input.context.profile.onboarding_completed:
            name = input.context.profile.preferred_name
            text = (
                f"Welcome back, {name}. Your delivery profile is available."
                if name
                else "Welcome back. Your delivery profile is available."
            )
            return CapabilityOutput(
                session=input.session.model_copy(
                    update={
                        "customer_onboarding": CustomerOnboardingState(
                            stage=OnboardingStage.COMPLETED
                        )
                    }
                ),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="customer-profile-already-saved", text=text
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="continue-shopping-returning-customer",
                        question="What would you like to order?",
                    ),
                    protected_values=(name,) if name else (),
                ),
            )
        try:
            name, phone, address = await self._service.get_onboarding_values(
                context.tenant_id, context.channel, context.channel_customer_id
            )
        except SavedDeliveryPersistenceError:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="customer-profile-temporarily-unavailable",
                            text="Customer profile memory is temporarily unavailable; no details were collected or changed.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="retry-customer-onboarding",
                        question="Would you like to try again?",
                    ),
                ),
            )
        requires_location = (
            self._require_whatsapp_location and context.channel is ChannelName.WHATSAPP
        )
        state = CustomerOnboardingState(
            delivery_input_mode=(
                DeliveryInputMode.WHATSAPP_LOCATION
                if requires_location
                else DeliveryInputMode.TEXT_ADDRESS
            ),
            pending_customer_name=name,
            pending_phone_number=phone,
            pending_address_details=None if requires_location else address,
        )
        state = with_resolved_stage(state)
        outcome = (
            review_outcome(state)
            if state.stage is OnboardingStage.REVIEWING_PROFILE
            else next_required_outcome(state, first_offer=True)
        )
        return CapabilityOutput(
            session=input.session.model_copy(update={"customer_onboarding": state}),
            outcome=outcome,
        )
