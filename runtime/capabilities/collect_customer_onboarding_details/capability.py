from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from commerce.models import CommerceSession, OnboardingStage
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
    correction_outcome,
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


class CollectCustomerOnboardingDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: NonEmptyText | None = None
    phone_number: NonEmptyText | None = None

    @model_validator(mode="after")
    def require_one_value(self):
        if not self.model_fields_set or not any(
            value is not None for value in (self.customer_name, self.phone_number)
        ):
            raise ValueError("At least one identity field is required.")
        return self


class CollectCustomerOnboardingDetailsCapability(Capability[CommerceSession]):
    def __init__(self, phone_policy: PhoneValidationPolicy) -> None:
        self._phone_policy = phone_policy

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.COLLECT_CUSTOMER_ONBOARDING_DETAILS,
            description="Collects sparse customer name and phone values during identity onboarding; at least one value is required.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        state = input.session.customer_onboarding
        if state.stage not in {
            OnboardingStage.COLLECTING_IDENTITY,
            OnboardingStage.REVIEWING_PROFILE,
        }:
            return self._not_active(input.session)
        if not input.data and state.stage is OnboardingStage.REVIEWING_PROFILE:
            return CapabilityOutput(session=input.session, outcome=correction_outcome())
        try:
            arguments = CollectCustomerOnboardingDetailsArguments.model_validate(
                input.data
            )
        except ValidationError:
            return self._invalid(input.session)

        if arguments.customer_name is not None and not any(
            character.isalnum() for character in arguments.customer_name
        ):
            return self._invalid(input.session, field="name")
        if arguments.phone_number is not None and not self._phone_policy.is_valid(
            arguments.phone_number
        ):
            return self._invalid(input.session, field="phone number")

        updates: dict[str, str] = {}
        if arguments.customer_name is not None:
            updates["pending_customer_name"] = arguments.customer_name
        if arguments.phone_number is not None:
            updates["pending_phone_number"] = arguments.phone_number
        state = with_resolved_stage(state.model_copy(update=updates))
        outcome = (
            review_outcome(state)
            if state.stage is OnboardingStage.REVIEWING_PROFILE
            else next_required_outcome(state)
        )
        if state.stage is OnboardingStage.COLLECTING_LOCATION:
            outcome = outcome.model_copy(
                update={
                    "fragments": (
                        ApprovedResponseFragment(
                            id="customer-identity-received",
                            text="Customer name and phone number were received.",
                        ),
                    )
                }
            )
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
                        id="customer-onboarding-identity-not-active",
                        text="Customer identity is not currently being collected.",
                    ),
                ),
            ),
        )

    @staticmethod
    def _invalid(
        session: CommerceSession, field: str = "identity detail"
    ) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="invalid-onboarding-identity",
                        text=f"The supplied {field} is invalid; previously accepted details were retained.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="correct-onboarding-identity",
                    question=f"Please share a valid {field}.",
                ),
            ),
        )
