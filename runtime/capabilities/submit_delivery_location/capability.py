from pydantic import BaseModel, ConfigDict, ValidationError

from channels.models import MessageKind
from commerce.models import (
    CheckoutStage,
    CommerceSession,
    DeliveryLocationSnapshot,
    OnboardingStage,
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
        if onboarding.stage in {
            OnboardingStage.COLLECTING_DETAILS,
            OnboardingStage.REVIEWING_DETAILS,
            OnboardingStage.NOT_STARTED,
        }:
            onboarding = onboarding.model_copy(
                update={
                    "stage": OnboardingStage.COLLECTING_DETAILS,
                    "pending_delivery_location": pending,
                    "pending_delivery_address": None,
                }
            )
            session = session.model_copy(update={"customer_onboarding": onboarding})
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
        elif (
            self._saved_details_service is not None
            and input.context.channel_customer_id is not None
        ):
            profile, addresses = await self._saved_details_service.list_addresses(
                input.context.tenant_id,
                input.context.channel,
                input.context.channel_customer_id,
            )
            address = next((item for item in addresses if item.is_default), None)
            address = address or (addresses[0] if addresses else None)
            if profile is not None and address is not None:
                onboarding = onboarding.model_copy(
                    update={
                        "stage": OnboardingStage.COLLECTING_DETAILS,
                        "pending_customer_name": profile.customer_name,
                        "pending_phone_number": profile.phone_number,
                        "pending_delivery_address": None,
                        "pending_delivery_location": pending,
                        "replacement_address_id": address.id,
                        "replacement_address_version": address.version,
                    }
                )
                session = session.model_copy(update={"customer_onboarding": onboarding})
        return CapabilityOutput(
            session=session,
            outcome=GeneratedExecutionOutcome(
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
