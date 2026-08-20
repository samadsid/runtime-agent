import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from commerce.models import CheckoutStage, CommerceSession, OnboardingStage, PendingDeliveryLocation
from runtime.capabilities import Capability, CapabilityInput, CapabilityMetadata, CapabilityName, CapabilityOutput
from runtime.capabilities.onboarding_support import missing_fields, missing_outcome, review_outcome
from runtime.capabilities.checkout_support import advance_to_payment
from runtime.contracts import ApprovedResponseFragment, ExecutionStatus, FollowUpRequest, GeneratedExecutionOutcome


class CollectDeliveryAddressDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_details: str = Field(min_length=1, max_length=500)

    @field_validator("address_details")
    @classmethod
    def clean(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", normalized):
            raise ValueError("invalid_address_details")
        return normalized


class CollectDeliveryAddressDetailsCapability(Capability[CommerceSession]):
    def __init__(self, payment_policy) -> None:
        self._payment_policy = payment_policy

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.COLLECT_DELIVERY_ADDRESS_DETAILS,
            description="Collects building-level details for an already checked delivery location.",
        )

    async def execute(self, input: CapabilityInput[CommerceSession]) -> CapabilityOutput[CommerceSession]:
        try:
            arguments = CollectDeliveryAddressDetailsArguments.model_validate(input.data)
        except ValidationError:
            return CapabilityOutput(session=input.session, outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(ApprovedResponseFragment(id="invalid-delivery-address-details", text="The building details are invalid; the checked location was retained."),),
                follow_up=FollowUpRequest(id="delivery-address-details-required", question="Please provide bounded flat or house, floor, entrance, and landmark details."),
            ))
        onboarding = input.session.customer_onboarding
        if onboarding.pending_delivery_location is not None and onboarding.stage in {OnboardingStage.COLLECTING_DETAILS, OnboardingStage.REVIEWING_DETAILS}:
            location = PendingDeliveryLocation.model_validate(
                onboarding.pending_delivery_location.model_dump()
                | {"address_details": arguments.address_details}
            )
            display = ", ".join(filter(None, (location.formatted_area, arguments.address_details)))
            onboarding = onboarding.model_copy(update={
                "pending_delivery_location": location,
                "pending_delivery_address": display,
            })
            if missing_fields(onboarding):
                onboarding = onboarding.model_copy(update={"stage": OnboardingStage.COLLECTING_DETAILS})
                outcome = missing_outcome(onboarding)
            else:
                onboarding = onboarding.model_copy(update={"stage": OnboardingStage.REVIEWING_DETAILS})
                outcome = review_outcome(onboarding)
            return CapabilityOutput(session=input.session.model_copy(update={"customer_onboarding": onboarding}), outcome=outcome)
        checkout = input.session.checkout
        if checkout.delivery_location is not None and checkout.stage is not CheckoutStage.NONE:
            location = checkout.delivery_location.model_copy(update={"address_details": arguments.address_details})
            display = ", ".join(filter(None, (location.formatted_area, arguments.address_details)))
            checkout = checkout.model_copy(update={"delivery_location": location, "delivery_address": display})
            checkout, outcome = await advance_to_payment(checkout, input.session.cart_items, input.context.tenant_id, self._payment_policy)
            return CapabilityOutput(session=input.session.model_copy(update={"checkout": checkout}), outcome=outcome)
        return CapabilityOutput(session=input.session, outcome=GeneratedExecutionOutcome(
            status=ExecutionStatus.INVALID_INPUT,
            fragments=(ApprovedResponseFragment(id="delivery-location-required", text="Building details require a checked delivery location first."),),
            follow_up=FollowUpRequest(id="share-delivery-location", question="Please send the delivery destination using the WhatsApp Location attachment."),
        ))
