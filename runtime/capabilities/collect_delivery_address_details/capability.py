import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from commerce.models import (
    CheckoutStage,
    CommerceSession,
    CustomerLocationUse,
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
from runtime.capabilities.checkout_support import (
    advance_to_payment,
    missing_detail_outcome,
)
from runtime.capabilities.onboarding_support import review_outcome, with_resolved_stage
from runtime.contracts import (
    ApprovedResponseFragment,
    ExecutionStatus,
    FollowUpRequest,
    GeneratedExecutionOutcome,
)


class CollectDeliveryAddressDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address_details: str = Field(min_length=1, max_length=500)

    @field_validator("address_details")
    @classmethod
    def clean(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if (
            not normalized
            or not any(character.isalnum() for character in normalized)
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", normalized)
        ):
            raise ValueError("invalid_address_details")
        return normalized


class CollectDeliveryAddressDetailsCapability(Capability[CommerceSession]):
    def __init__(
        self,
        payment_policy,
        saved_details_service: SavedDeliveryDetailsService | None = None,
    ) -> None:
        self._payment_policy = payment_policy
        self._saved_details_service = saved_details_service

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
        pending_customer_location = input.session.pending_customer_location
        if pending_customer_location is not None:
            if pending_customer_location.use is None:
                return CapabilityOutput(
                    session=input.session,
                    outcome=GeneratedExecutionOutcome(
                        status=ExecutionStatus.MISSING_INPUT,
                        fragments=(
                            ApprovedResponseFragment(
                                id="customer-location-use-required",
                                text="The shared location has not been assigned a use yet.",
                            ),
                        ),
                        follow_up=FollowUpRequest(
                            id="choose-customer-location-use",
                            question="Should this location be saved as a new address or used only for the current order?",
                        ),
                    ),
                )
            location = pending_customer_location.delivery_location.model_copy(
                update={"address_details": arguments.address_details}
            )
            display = ", ".join(
                filter(None, (location.formatted_area, arguments.address_details))
            )
            pending_customer_location = pending_customer_location.model_copy(
                update={
                    "delivery_location": location,
                    "address_details": arguments.address_details,
                }
            )
            session = input.session.model_copy(
                update={"pending_customer_location": pending_customer_location}
            )
            if (
                pending_customer_location.use
                is CustomerLocationUse.SAVE_NEW_ADDRESS
            ):
                if self._saved_details_service is None:
                    return self._save_failure(session)
                try:
                    profile = await self._saved_details_service.get_profile(
                        input.context.tenant_id,
                        input.context.channel,
                        input.context.channel_customer_id,
                    )
                    if profile is None:
                        return self._save_failure(session)
                    await self._saved_details_service.add_address(
                        input.context.tenant_id,
                        input.context.channel_customer_id,
                        profile.id,
                        "Other",
                        display,
                        location,
                        set_as_default=False,
                    )
                    session = session.model_copy(update={"recent_saved_addresses": ()})
                except SavedDeliveryPersistenceError:
                    return self._save_failure(session)
            checkout = session.checkout
            if checkout.stage in {
                CheckoutStage.COLLECTING_DETAILS,
                CheckoutStage.READY_TO_CONFIRM,
                CheckoutStage.SELECTING_PAYMENT_METHOD,
            }:
                checkout = checkout.model_copy(
                    update={
                        "stage": CheckoutStage.COLLECTING_DETAILS,
                        "delivery_location": location,
                        "delivery_address": display,
                        "payment_method": None,
                    }
                )
                session = session.model_copy(
                    update={
                        "checkout": checkout,
                        "pending_customer_location": None,
                    }
                )
                if all(
                    (
                        checkout.customer_name,
                        checkout.phone_number,
                        checkout.delivery_address,
                    )
                ):
                    checkout, outcome = await advance_to_payment(
                        checkout,
                        session.cart_items,
                        input.context.tenant_id,
                        self._payment_policy,
                    )
                    session = session.model_copy(update={"checkout": checkout})
                else:
                    outcome = missing_detail_outcome(checkout)
                return CapabilityOutput(session=session, outcome=outcome)
            return CapabilityOutput(
                session=session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id=(
                                "alternative-delivery-address-saved"
                                if pending_customer_location.use
                                is CustomerLocationUse.SAVE_NEW_ADDRESS
                                else "temporary-delivery-address-ready"
                            ),
                            text=(
                                "The new non-default address was saved and selected for the next checkout."
                                if pending_customer_location.use
                                is CustomerLocationUse.SAVE_NEW_ADDRESS
                                else "The temporary address was selected for the next checkout and was not saved."
                            ),
                        ),
                    ),
                ),
            )
        onboarding = input.session.customer_onboarding
        if onboarding.stage in {
            OnboardingStage.COLLECTING_ADDRESS_DETAILS,
            OnboardingStage.REVIEWING_PROFILE,
        } and (
            onboarding.delivery_input_mode is DeliveryInputMode.TEXT_ADDRESS
            or onboarding.pending_delivery_location is not None
        ):
            location = onboarding.pending_delivery_location
            if location is not None:
                location = location.model_copy(
                    update={"address_details": arguments.address_details}
                )
            onboarding = with_resolved_stage(onboarding.model_copy(update={
                "pending_delivery_location": location,
                "pending_address_details": arguments.address_details,
            }))
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

    @staticmethod
    def _save_failure(session: CommerceSession) -> CapabilityOutput[CommerceSession]:
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.FAILURE,
                fragments=(
                    ApprovedResponseFragment(
                        id="alternative-delivery-address-save-failed",
                        text="The new address could not be saved temporarily; the proposal was retained.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="retry-alternative-address-save",
                    question="Would you like to retry saving this address?",
                ),
            ),
        )
