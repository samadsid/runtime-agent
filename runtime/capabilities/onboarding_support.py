from __future__ import annotations

from commerce.models import CustomerOnboardingState, ProfileField
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
    ResponseFragmentKind,
)

FIELD_LABELS = {
    ProfileField.CUSTOMER_NAME: "name",
    ProfileField.PHONE_NUMBER: "phone number",
    ProfileField.DELIVERY_ADDRESS: "complete delivery address",
}


def missing_fields(state: CustomerOnboardingState) -> tuple[ProfileField, ...]:
    values = {
        ProfileField.CUSTOMER_NAME: state.pending_customer_name,
        ProfileField.PHONE_NUMBER: state.pending_phone_number,
        ProfileField.DELIVERY_ADDRESS: state.pending_delivery_address,
    }
    return tuple(field for field, value in values.items() if value is None)


def missing_outcome(
    state: CustomerOnboardingState, *, first_offer: bool = False
) -> GeneratedExecutionOutcome:
    fields = missing_fields(state)
    requested = ", ".join(FIELD_LABELS[field] for field in fields)
    return GeneratedExecutionOutcome(
        status=ExecutionStatus.MISSING_INPUT,
        fragments=(
            (
                ApprovedResponseFragment(
                    id="customer-onboarding-welcome",
                    text="Welcome to MeatUncle!",
                )
                if first_offer
                else ApprovedResponseFragment(
                    id="customer-onboarding-incomplete",
                    text="The valid details supplied so far have been retained for this review.",
                )
            ),
            *(
                (
                    ApprovedResponseFragment(
                        id="customer-onboarding-started",
                        text="To help with ordering and delivery, your details will be saved for future orders.",
                    ),
                )
                if first_offer
                else ()
            ),
        ),
        follow_up=FollowUpRequest(
            id="request-customer-profile"
            if first_offer
            else "request-missing-profile-details",
            question=f"What {requested} would you like me to save? You may reply as Name, Phone, and Complete address.",
        ),
    )


def review_outcome(state: CustomerOnboardingState) -> GeneratedExecutionOutcome:
    assert state.pending_customer_name is not None
    assert state.pending_phone_number is not None
    assert state.pending_delivery_address is not None
    values = (
        f"Name: {state.pending_customer_name}",
        f"Phone: {state.pending_phone_number}",
        f"Address: {state.pending_delivery_address}",
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
        protected_values=(
            state.pending_customer_name,
            state.pending_phone_number,
            state.pending_delivery_address,
        ),
    )
