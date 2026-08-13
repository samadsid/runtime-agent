from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from commerce.models import CommerceSession, OnboardingStage, ProfileField
from commerce.services import PhoneValidationPolicy
from runtime.capabilities import (
    Capability,
    CapabilityInput,
    CapabilityMetadata,
    CapabilityName,
    CapabilityOutput,
)
from runtime.capabilities.checkout_support import NonEmptyText
from runtime.capabilities.onboarding_support import (
    FIELD_LABELS,
    missing_fields,
    missing_outcome,
    review_outcome,
)
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class CollectCustomerOnboardingDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None
    delivery_address: NonEmptyText | None = None


class CollectCustomerOnboardingDetailsCapability(Capability[CommerceSession]):
    def __init__(self, phone_policy: PhoneValidationPolicy) -> None:
        self._phone_policy = phone_policy

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.COLLECT_CUSTOMER_ONBOARDING_DETAILS,
            description="Collects any confidently extracted onboarding name, phone, and address into a review proposal; all arguments are optional.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        state = input.session.customer_onboarding
        if state.stage not in {
            OnboardingStage.COLLECTING_DETAILS,
            OnboardingStage.REVIEWING_DETAILS,
        }:
            return self._not_active(input.session)
        try:
            arguments = CollectCustomerOnboardingDetailsArguments.model_validate(
                input.data
            )
        except ValidationError as error:
            field = error.errors()[0].get("loc", (None,))[0]
            return self._invalid(input.session, str(field) if field else None)
        for field in ("customer_name", "phone_number", "delivery_address"):
            if (
                field in arguments.model_fields_set
                and getattr(arguments, field) is None
            ):
                return self._invalid(input.session, field)
        updates = {
            f"pending_{field}": value
            for field, value in arguments.model_dump().items()
            if value is not None
        }
        state = state.model_copy(update=updates)
        if arguments.phone_number is not None and not self._phone_policy.is_valid(
            arguments.phone_number
        ):
            state = state.model_copy(
                update={
                    "pending_phone_number": None,
                    "stage": OnboardingStage.COLLECTING_DETAILS,
                }
            )
            remaining = missing_fields(state)
            requested = ", ".join(FIELD_LABELS[field] for field in remaining)
            return CapabilityOutput(
                session=input.session.model_copy(update={"customer_onboarding": state}),
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.INVALID_INPUT,
                    fragments=(
                        ApprovedResponseFragment(
                            id="invalid-onboarding-phone",
                            text="The supplied phone number does not satisfy the delivery policy; the other valid details were retained.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="correct-onboarding-details",
                        question=f"What valid {requested} should I use?",
                    ),
                ),
            )
        if missing_fields(state):
            state = state.model_copy(
                update={"stage": OnboardingStage.COLLECTING_DETAILS}
            )
            outcome = missing_outcome(state)
        elif not input.data and state.stage is OnboardingStage.REVIEWING_DETAILS:
            outcome = GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="customer-onboarding-review-rejected",
                        text="The proposed profile has not been saved or changed.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-onboarding-details",
                    question="Which name, phone number, or address should be corrected?",
                ),
            )
        else:
            state = state.model_copy(
                update={"stage": OnboardingStage.REVIEWING_DETAILS}
            )
            outcome = review_outcome(state)
        return CapabilityOutput(
            session=input.session.model_copy(update={"customer_onboarding": state}),
            outcome=outcome,
        )

    @staticmethod
    def _not_active(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="customer-onboarding-not-active",
                        text="Customer onboarding is not currently collecting details.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="start-customer-onboarding",
                    question="Would you like to save delivery details for future orders?",
                ),
            ),
        )

    @staticmethod
    def _invalid(
        session: CommerceSession, field: str | None
    ) -> CapabilityOutput[CommerceSession]:
        label = (
            FIELD_LABELS.get(ProfileField(field), "detail")
            if field in {item.value for item in ProfileField}
            else "detail"
        )
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-onboarding-details",
                        text=f"The supplied {label} is invalid; other pending details were preserved.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-onboarding-details",
                    question="What valid missing or corrected profile details should I use?",
                ),
            ),
        )
