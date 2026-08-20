from __future__ import annotations

from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerOnboardingState,
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
from runtime.capabilities.onboarding_support import missing_outcome, review_outcome
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
        state = CustomerOnboardingState(
            stage=OnboardingStage.COLLECTING_DETAILS,
            pending_customer_name=name,
            pending_phone_number=phone,
            pending_delivery_address=address,
        )
        requires_location = (
            self._require_whatsapp_location and context.channel is ChannelName.WHATSAPP
        )
        if requires_location:
            state = state.model_copy(update={"pending_delivery_address": None})
            return CapabilityOutput(
                session=input.session.model_copy(update={"customer_onboarding": state}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.MISSING_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="delivery-location-requested",
                            text="To save reusable delivery details, share your name and phone number plus the WhatsApp location attachment for the delivery destination.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="share-onboarding-details-and-location",
                        question="Please share any missing name or phone number and send the delivery destination using WhatsApp Location.",
                    ),
                ),
            )
        outcome = (
            review_outcome(
                state.model_copy(update={"stage": OnboardingStage.REVIEWING_DETAILS})
            )
            if all((name, phone, address))
            else missing_outcome(state, first_offer=True)
        )
        if all((name, phone, address)):
            state = state.model_copy(
                update={"stage": OnboardingStage.REVIEWING_DETAILS}
            )
        return CapabilityOutput(
            session=input.session.model_copy(update={"customer_onboarding": state}),
            outcome=outcome,
        )
