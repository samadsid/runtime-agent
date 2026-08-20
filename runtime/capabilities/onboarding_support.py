from __future__ import annotations

from commerce.models import (
    CustomerOnboardingState,
    DeliveryInputMode,
    OnboardingStage,
)
from runtime.capabilities.checkout_support import mask_phone
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)


def resolve_onboarding_stage(state: CustomerOnboardingState) -> OnboardingStage:
    """Resolve the single active onboarding stage from retained proposal values."""
    if not state.pending_customer_name or not state.pending_phone_number:
        return OnboardingStage.COLLECTING_IDENTITY
    if (
        state.delivery_input_mode is DeliveryInputMode.WHATSAPP_LOCATION
        and state.pending_delivery_location is None
    ):
        return OnboardingStage.COLLECTING_LOCATION
    if not state.pending_address_details:
        return OnboardingStage.COLLECTING_ADDRESS_DETAILS
    return OnboardingStage.REVIEWING_PROFILE


def with_resolved_stage(state: CustomerOnboardingState) -> CustomerOnboardingState:
    return state.model_copy(update={"stage": resolve_onboarding_stage(state)})


def next_required_outcome(
    state: CustomerOnboardingState, *, first_offer: bool = False
) -> GeneratedExecutionOutcome:
    stage = resolve_onboarding_stage(state)
    fragments: tuple[ApprovedResponseFragment, ...] = ()
    if first_offer:
        fragments = (
            ApprovedResponseFragment(
                id="customer-onboarding-welcome",
                text="Welcome to MeatUncle!",
            ),
        )

    if stage is OnboardingStage.COLLECTING_IDENTITY:
        if state.pending_customer_name is None and state.pending_phone_number is None:
            follow_up = FollowUpRequest(
                id="request-customer-identity",
                question="Please share your name and phone number to get started.",
            )
        elif state.pending_customer_name is None:
            follow_up = FollowUpRequest(
                id="request-customer-name",
                question="Please share your name.",
            )
        else:
            follow_up = FollowUpRequest(
                id="request-customer-phone",
                question="Please share a valid phone number.",
            )
    elif stage is OnboardingStage.COLLECTING_LOCATION:
        follow_up = FollowUpRequest(
            id="request-delivery-location",
            question="Please share the delivery destination using WhatsApp Location.",
        )
    else:
        follow_up = FollowUpRequest(
            id="request-address-details",
            question=(
                "Please share the flat or house number, floor, entrance, and a nearby landmark."
                if state.delivery_input_mode is DeliveryInputMode.WHATSAPP_LOCATION
                else "Please share the complete delivery address."
            ),
        )
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=fragments,
        follow_up=follow_up,
    )


def review_outcome(state: CustomerOnboardingState) -> GeneratedExecutionOutcome:
    assert state.pending_customer_name is not None
    assert state.pending_phone_number is not None
    assert state.pending_address_details is not None
    masked_phone = mask_phone(state.pending_phone_number)
    area = (
        state.pending_delivery_location.formatted_area
        if state.pending_delivery_location is not None
        else None
    )
    address = ", ".join(
        value for value in (area, state.pending_address_details) if value
    )
    values = (
        f"Name: {state.pending_customer_name}",
        f"Phone: {masked_phone}",
        f"Address: {address}",
    )
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=(
            ApprovedResponseFragment(
                id="customer-onboarding-review",
                text="Please review the proposed delivery profile. It has not been saved yet.",
            ),
            *(
                ApprovedResponseFragment(
                    id=f"customer-onboarding-review-{index}",
                    text=value,
                    kind=ResponseFragmentKind.ITEM,
                )
                for index, value in enumerate(values, start=1)
            ),
        ),
        follow_up=FollowUpRequest(
            id="confirm-customer-profile",
            question="Are these details correct and do you confirm saving them for future orders?",
        ),
        protected_values=(state.pending_customer_name, masked_phone, address),
    )


def correction_outcome() -> GeneratedExecutionOutcome:
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=(
            ApprovedResponseFragment(
                id="customer-onboarding-review-rejected",
                text="The proposed profile has not been saved or changed.",
            ),
        ),
        follow_up=FollowUpRequest(
            id="correct-onboarding-details",
            question="Which name, phone number, delivery location, or address detail should be changed?",
        ),
    )
