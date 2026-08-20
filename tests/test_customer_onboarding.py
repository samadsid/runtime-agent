from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from channels.models import MessageKind
from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerOnboardingState,
    DeliveryInputMode,
    InboundLocation,
    OnboardingStage,
    PendingDeliveryLocation,
    SavedDeliveryProfile,
    ServiceabilityKind,
    ServiceabilityResult,
)
from commerce.services import DisabledReverseGeocoder, NonEmptyPhoneValidationPolicy
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.collect_customer_onboarding_details import (
    CollectCustomerOnboardingDetailsCapability,
)
from runtime.capabilities.collect_delivery_address_details import (
    CollectDeliveryAddressDetailsCapability,
)
from runtime.capabilities.confirm_customer_onboarding import (
    ConfirmCustomerOnboardingCapability,
)
from runtime.capabilities.onboarding_support import (
    next_required_outcome,
    resolve_onboarding_stage,
)
from runtime.capabilities.skip_customer_onboarding import (
    SkipCustomerOnboardingCapability,
)
from runtime.capabilities.start_customer_onboarding import (
    StartCustomerOnboardingCapability,
)
from runtime.capabilities.submit_delivery_location import (
    SubmitDeliveryLocationCapability,
)
from runtime.capabilities.use_text_address_for_onboarding import (
    UseTextAddressForOnboardingCapability,
)
from runtime.contracts import TrustedInboundMessageContext


def input_for(session: CommerceSession, data: dict[str, object] | None = None):
    return CapabilityInput[CommerceSession](
        session=session,
        data=data or {},
        context=ExecutionContext(
            tenant_id=uuid4(),
            conversation_id=uuid4(),
            channel=ChannelName.WHATSAPP,
            channel_customer_id="customer-1",
            request_id="whatsapp:request-1",
        ),
    )


def pending_location() -> PendingDeliveryLocation:
    return PendingDeliveryLocation(
        latitude=Decimal("28.6"),
        longitude=Decimal("77.2"),
        zone_id=uuid4(),
        zone_name="Delhi East",
        zone_version=1,
        formatted_area="DDA Colony",
        checked_at=datetime.now(timezone.utc),
        source_inbound_message_id=uuid4(),
    )


def whatsapp_state(**updates: object) -> CustomerOnboardingState:
    return CustomerOnboardingState(
        delivery_input_mode=DeliveryInputMode.WHATSAPP_LOCATION,
        **updates,
    )


def test_stage_resolver_is_sequential() -> None:
    empty = whatsapp_state()
    named = empty.model_copy(update={"pending_customer_name": "Samad"})
    identified = named.model_copy(update={"pending_phone_number": "9560717170"})
    located = identified.model_copy(update={"pending_delivery_location": pending_location()})
    addressed = located.model_copy(update={"pending_address_details": "B-68, 2nd Floor"})

    assert resolve_onboarding_stage(empty) is OnboardingStage.COLLECTING_IDENTITY
    assert resolve_onboarding_stage(named) is OnboardingStage.COLLECTING_IDENTITY
    assert resolve_onboarding_stage(identified) is OnboardingStage.COLLECTING_LOCATION
    assert resolve_onboarding_stage(located) is OnboardingStage.COLLECTING_ADDRESS_DETAILS
    assert resolve_onboarding_stage(addressed) is OnboardingStage.REVIEWING_PROFILE


def test_first_offer_greets_and_requests_identity_only() -> None:
    outcome = next_required_outcome(whatsapp_state(), first_offer=True)

    assert [fragment.id for fragment in outcome.fragments] == [
        "customer-onboarding-welcome"
    ]
    assert outcome.follow_up is not None
    assert outcome.follow_up.id == "request-customer-identity"
    assert "location" not in outcome.follow_up.question.lower()
    assert "address" not in outcome.follow_up.question.lower()


@pytest.mark.asyncio
async def test_sparse_identity_is_retained_and_only_missing_value_requested() -> None:
    capability = CollectCustomerOnboardingDetailsCapability(
        NonEmptyPhoneValidationPolicy()
    )
    session = CommerceSession(
        customer_onboarding=whatsapp_state(stage=OnboardingStage.COLLECTING_IDENTITY)
    )

    named = await capability.execute(input_for(session, {"customer_name": "Samad"}))
    assert named.session.customer_onboarding.pending_customer_name == "Samad"
    assert named.outcome.follow_up is not None
    assert named.outcome.follow_up.id == "request-customer-phone"

    identified = await capability.execute(
        input_for(named.session, {"phone_number": "9560717170"})
    )
    assert identified.session.customer_onboarding.stage is OnboardingStage.COLLECTING_LOCATION
    assert identified.outcome.follow_up is not None
    assert identified.outcome.follow_up.id == "request-delivery-location"
    assert "complete delivery address" not in str(identified.outcome)


@pytest.mark.asyncio
async def test_invalid_sparse_update_preserves_existing_valid_values() -> None:
    class RejectingPhonePolicy:
        def is_valid(self, phone_number: str) -> bool:
            return phone_number.isdigit() and len(phone_number) == 10

    capability = CollectCustomerOnboardingDetailsCapability(RejectingPhonePolicy())
    state = whatsapp_state(
        stage=OnboardingStage.COLLECTING_IDENTITY,
        pending_customer_name="Samad",
    )
    result = await capability.execute(
        input_for(CommerceSession(customer_onboarding=state), {"phone_number": "x"})
    )

    assert result.session.customer_onboarding == state
    assert result.outcome.status.value == "invalid_input"


@pytest.mark.asyncio
async def test_address_details_create_masked_review_without_coordinates() -> None:
    capability = CollectDeliveryAddressDetailsCapability(object())
    state = whatsapp_state(
        stage=OnboardingStage.COLLECTING_ADDRESS_DETAILS,
        pending_customer_name="Samad",
        pending_phone_number="9560717170",
        pending_delivery_location=pending_location(),
    )
    result = await capability.execute(
        input_for(
            CommerceSession(customer_onboarding=state),
            {"address_details": "B-68, 2nd Floor, near XYZ School"},
        )
    )

    assert result.session.customer_onboarding.stage is OnboardingStage.REVIEWING_PROFILE
    assert "******7170" in str(result.outcome)
    assert "9560717170" not in str(result.outcome)
    assert "28.6" not in str(result.outcome)
    assert result.outcome.follow_up is not None
    assert result.outcome.follow_up.id == "confirm-customer-profile"


@pytest.mark.asyncio
async def test_explicit_location_fallback_switches_mode_and_requests_address() -> None:
    state = whatsapp_state(
        stage=OnboardingStage.COLLECTING_LOCATION,
        pending_customer_name="Samad",
        pending_phone_number="9560717170",
    )
    result = await UseTextAddressForOnboardingCapability().execute(
        input_for(CommerceSession(customer_onboarding=state))
    )

    assert result.session.customer_onboarding.delivery_input_mode is DeliveryInputMode.TEXT_ADDRESS
    assert result.session.customer_onboarding.stage is OnboardingStage.COLLECTING_ADDRESS_DETAILS
    assert result.outcome.follow_up is not None
    assert result.outcome.follow_up.id == "request-address-details"


class RecordingOnboardingService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    async def complete_onboarding(self, *args: object) -> SavedDeliveryProfile:
        self.calls.append(args)
        return SavedDeliveryProfile(
            id=uuid4(),
            tenant_id=args[0] if isinstance(args[0], UUID) else UUID(int=0),
            channel=ChannelName.WHATSAPP,
            channel_customer_id="customer-1",
            customer_name="Samad",
            phone_number="9560717170",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    async def get_onboarding_values(self, *args: object):
        return None, None, None


class ServiceableDeliveryService:
    async def check_serviceability(self, tenant_id, latitude, longitude):
        return ServiceabilityResult(
            kind=ServiceabilityKind.SERVICEABLE,
            zone_id=uuid4(),
            zone_name="Delhi East",
            zone_version=1,
            checked_at=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_required_sequential_onboarding_regression() -> None:
    service = RecordingOnboardingService()
    start = StartCustomerOnboardingCapability(  # type: ignore[arg-type]
        service, require_whatsapp_location=True
    )
    identity = CollectCustomerOnboardingDetailsCapability(
        NonEmptyPhoneValidationPolicy()
    )
    location = SubmitDeliveryLocationCapability(  # type: ignore[arg-type]
        ServiceableDeliveryService(), DisabledReverseGeocoder()
    )
    address = CollectDeliveryAddressDetailsCapability(object())
    confirm = ConfirmCustomerOnboardingCapability(service)  # type: ignore[arg-type]

    started = await start.execute(input_for(CommerceSession()))
    identified = await identity.execute(
        input_for(
            started.session,
            {"customer_name": "Samad", "phone_number": "9560717170"},
        )
    )
    inbound_id = uuid4()
    location_input = input_for(identified.session)
    location_input = location_input.model_copy(
        update={
            "context": location_input.context.model_copy(
                update={
                    "inbound_message": TrustedInboundMessageContext(
                        inbound_message_id=inbound_id,
                        request_id="whatsapp:request-1",
                        message_kind=MessageKind.LOCATION,
                        location=InboundLocation(latitude="28.6", longitude="77.2"),
                    )
                }
            )
        }
    )
    located = await location.execute(location_input)
    addressed = await address.execute(
        input_for(
            located.session,
            {"address_details": "B-68, 2nd Floor, near XYZ School"},
        )
    )
    confirmed = await confirm.execute(input_for(addressed.session))

    outcomes = (
        started.outcome,
        identified.outcome,
        located.outcome,
        addressed.outcome,
        confirmed.outcome,
    )
    assert [outcome.follow_up.id if outcome.follow_up else None for outcome in outcomes] == [
        "request-customer-identity",
        "request-delivery-location",
        "delivery-address-details-required",
        "confirm-customer-profile",
        None,
    ]
    assert confirmed.session.customer_onboarding.stage is OnboardingStage.COMPLETED
    assert len(service.calls) == 1
    assert all(
        "Name, Phone, and Complete address" not in str(outcome)
        for outcome in outcomes
    )


@pytest.mark.asyncio
async def test_confirmation_persists_reviewed_values_once_and_completes() -> None:
    service = RecordingOnboardingService()
    state = whatsapp_state(
        stage=OnboardingStage.REVIEWING_PROFILE,
        pending_customer_name="Samad",
        pending_phone_number="9560717170",
        pending_address_details="B-68, 2nd Floor",
        pending_delivery_location=pending_location(),
    )
    result = await ConfirmCustomerOnboardingCapability(service).execute(  # type: ignore[arg-type]
        input_for(CommerceSession(customer_onboarding=state))
    )

    assert len(service.calls) == 1
    assert result.session.customer_onboarding.stage is OnboardingStage.COMPLETED
    assert result.outcome.follow_up is None
    assert "Welcome back" not in str(result.outcome)


@pytest.mark.asyncio
async def test_skip_clears_pending_personal_data() -> None:
    session = CommerceSession(
        customer_onboarding=whatsapp_state(
            stage=OnboardingStage.COLLECTING_IDENTITY,
            pending_customer_name="Samad",
        )
    )

    result = await SkipCustomerOnboardingCapability().execute(input_for(session))

    assert result.session.customer_onboarding == CustomerOnboardingState(
        stage=OnboardingStage.SKIPPED
    )
    assert result.session.deferred_customer_intent is None
