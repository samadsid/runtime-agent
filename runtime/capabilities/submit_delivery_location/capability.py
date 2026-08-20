from pydantic import BaseModel, ConfigDict, ValidationError

from channels.models import MessageKind
from commerce.models import (
    CheckoutStage,
    CommerceSession,
    DeliveryLocationSnapshot,
    OnboardingStage,
    PendingCustomerLocation,
    PendingDeliveryLocation,
    ServiceabilityKind,
)
from commerce.services import (
    DeliveryService,
    ReverseGeocoder,
    SavedDeliveryDetailsService,
)
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


class SubmitDeliveryLocationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubmitDeliveryLocationCapability(Capability[CommerceSession]):
    def __init__(
        self,
        delivery_service: DeliveryService,
        reverse_geocoder: ReverseGeocoder,
        saved_details_service: SavedDeliveryDetailsService | None = None,
    ) -> None:
        self._delivery_service = delivery_service
        self._reverse_geocoder = reverse_geocoder
        self._saved_details_service = saved_details_service

    @property
    def metadata(self) -> CapabilityMetadata:
        return CapabilityMetadata(
            name=CapabilityName.SUBMIT_DELIVERY_LOCATION,
            description="Checks the current trusted location attachment for delivery serviceability; takes no arguments.",
        )

    async def execute(
        self, input: CapabilityInput[CommerceSession]
    ) -> CapabilityOutput[CommerceSession]:
        try:
            SubmitDeliveryLocationArguments.model_validate(input.data)
        except ValidationError:
            return self._invalid(input.session)
        if (
            input.session.customer_onboarding.stage
            is OnboardingStage.COLLECTING_IDENTITY
        ):
            return CapabilityOutput(
                session=input.session,
                outcome=next_required_outcome(input.session.customer_onboarding),
            )
        trusted = input.context.inbound_message
        if (
            trusted is None
            or trusted.message_kind is not MessageKind.LOCATION
            or trusted.location is None
        ):
            return self._invalid(input.session)
        location = trusted.location
        result = await self._delivery_service.check_serviceability(
            input.context.tenant_id, location.latitude, location.longitude
        )
        if result.kind is ServiceabilityKind.TEMPORARILY_UNAVAILABLE:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.FAILURE,
                    fragments=(
                        ApprovedResponseFragment(
                            id="delivery-serviceability-temporarily-unavailable",
                            text="Delivery coverage could not be checked temporarily. The location has not been saved or rejected.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="retry-delivery-location",
                        question="Would you like to retry this location check?",
                    ),
                ),
            )
        if result.kind is ServiceabilityKind.OUTSIDE_SERVICE_AREA:
            return CapabilityOutput(
                session=input.session,
                outcome=GeneratedExecutionOutcome(
                    status=ExecutionStatus.SUCCESS,
                    fragments=(
                        ApprovedResponseFragment(
                            id="delivery-location-outside-area",
                            text="Delivery is not currently available at this location.",
                        ),
                    ),
                    follow_up=FollowUpRequest(
                        id="try-another-delivery-location",
                        question="Would you like to check another delivery location?",
                    ),
                ),
            )
        enrichment = await self._reverse_geocoder.reverse_geocode(
            location.latitude, location.longitude
        )
        area = enrichment.formatted_area or enrichment.locality or location.name
        assert result.zone_id and result.zone_name and result.zone_version
        pending = PendingDeliveryLocation(
            latitude=location.latitude,
            longitude=location.longitude,
            zone_id=result.zone_id,
            zone_name=result.zone_name,
            zone_version=result.zone_version,
            formatted_area=area,
            checked_at=result.checked_at,
            source_inbound_message_id=trusted.inbound_message_id,
        )
        session = input.session
        onboarding = session.customer_onboarding
        onboarding_outcome = None
        if onboarding.stage in {
            OnboardingStage.COLLECTING_LOCATION,
            OnboardingStage.COLLECTING_ADDRESS_DETAILS,
            OnboardingStage.REVIEWING_PROFILE,
        }:
            onboarding = with_resolved_stage(onboarding.model_copy(
                update={
                    "pending_delivery_location": pending,
                    "pending_address_details": None,
                }
            ))
            session = session.model_copy(update={"customer_onboarding": onboarding})
            if onboarding.stage is OnboardingStage.REVIEWING_PROFILE:
                onboarding_outcome = review_outcome(onboarding)
        elif (
            onboarding.stage is OnboardingStage.COMPLETED
            or input.context.profile.onboarding_completed
        ):
            session = session.model_copy(
                update={
                    "pending_customer_location": PendingCustomerLocation(
                        delivery_location=pending
                    )
                }
            )
            onboarding_outcome = GeneratedExecutionOutcome(
                status=ExecutionStatus.MISSING_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="customer-location-serviceable",
                        text=(
                            f"Delivery is available in {area}."
                            if area
                            else "Delivery is available at this location."
                        ),
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="choose-customer-location-use",
                    question="Should this location be saved as a new address or used only for the current order?",
                ),
                protected_values=(area,) if area else (),
            )
        elif session.checkout.stage in {
            CheckoutStage.COLLECTING_DETAILS,
            CheckoutStage.READY_TO_CONFIRM,
            CheckoutStage.SELECTING_PAYMENT_METHOD,
        }:
            checkout = session.checkout.model_copy(
                update={
                    "stage": CheckoutStage.COLLECTING_DETAILS,
                    "delivery_location": DeliveryLocationSnapshot.model_validate(
                        pending.model_dump()
                    ),
                    "delivery_address": None,
                    "payment_method": None,
                }
            )
            session = session.model_copy(update={"checkout": checkout})
        return CapabilityOutput(
            session=session,
            outcome=onboarding_outcome or GeneratedExecutionOutcome(
                status=ExecutionStatus.SUCCESS,
                fragments=(
                    ApprovedResponseFragment(
                        id="delivery-location-serviceable",
                        text=(
                            f"Delivery is available in {area}."
                            if area
                            else "Delivery is available at this location."
                        ),
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="delivery-address-details-required",
                    question="Please share the flat or house number, floor, entrance, and a nearby landmark.",
                ),
                protected_values=(area,) if area else (),
            ),
        )

    @staticmethod
    def _invalid(session):
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
                status=ExecutionStatus.INVALID_INPUT,
                fragments=(
                    ApprovedResponseFragment(
                        id="location-message-invalid",
                        text="A valid current location attachment is required; coordinates cannot be supplied as text.",
                    ),
                ),
                follow_up=FollowUpRequest(
                    id="share-delivery-location",
                    question="Please send the delivery destination using the WhatsApp Location attachment.",
                ),
            ),
        )
