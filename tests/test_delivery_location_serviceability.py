from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from channels.models import MessageKind
from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerLocationUse,
    CustomerOnboardingState,
    DeliveryInputMode,
    DeliveryZone,
    DeliveryZoneStatus,
    InboundLocation,
    OnboardingStage,
    OnboardingStatus,
    PendingCustomerLocation,
    PendingDeliveryLocation,
    SavedDeliveryAddress,
    SavedDeliveryProfile,
    ServiceabilityKind,
)
from commerce.repositories import DeliveryZoneRepository
from commerce.services import DeliveryService, DisabledReverseGeocoder
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.choose_customer_location_use import (
    ChooseCustomerLocationUseCapability,
)
from runtime.capabilities.collect_delivery_address_details import (
    CollectDeliveryAddressDetailsCapability,
)
from runtime.capabilities.submit_delivery_location import (
    SubmitDeliveryLocationCapability,
)
from runtime.contracts import TrustedInboundMessageContext


class ZoneRepository(DeliveryZoneRepository):
    def __init__(self, zone: DeliveryZone | None = None, fail: bool = False) -> None:
        self.zone = zone
        self.fail = fail
        self.received = None

    async def find_serviceable_zone(self, tenant_id, latitude, longitude):
        self.received = (tenant_id, latitude, longitude)
        if self.fail:
            raise RuntimeError("postgis unavailable")
        return self.zone

    async def list_zones(self, tenant_id, *, status, limit, cursor):
        return ()

    async def get_zone(self, tenant_id, zone_id):
        return self.zone


class SavedDetails:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.profile = SavedDeliveryProfile(
            id=uuid4(),
            tenant_id=UUID(int=1),
            channel=ChannelName.WHATSAPP,
            channel_customer_id="+919999999999",
            customer_name="Samad",
            phone_number="9999999999",
            onboarding_status=OnboardingStatus.COMPLETED,
            profile_consent_version="v1",
            profile_consented_at=now,
            created_at=now,
            updated_at=now,
        )
        self.address = SavedDeliveryAddress(
            id=uuid4(),
            profile_id=self.profile.id,
            label="Home",
            delivery_address="Old address",
            is_default=True,
            version=4,
            created_at=now,
            updated_at=now,
        )
        self.added: list[tuple[object, ...]] = []

    async def list_addresses(self, tenant_id, channel, customer_id):
        return self.profile, (self.address,)

    async def get_profile(self, tenant_id, channel, customer_id):
        return self.profile

    async def add_address(self, *args, **kwargs):
        self.added.append((*args, kwargs))
        return self.address


def active_zone() -> DeliveryZone:
    now = datetime.now(timezone.utc)
    return DeliveryZone(
        id=uuid4(),
        tenant_id=UUID(int=1),
        name="Delhi East",
        status=DeliveryZoneStatus.ACTIVE,
        priority=10,
        version=3,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_submit_location_reads_only_trusted_attachment_and_stores_pending() -> (
    None
):
    repository = ZoneRepository(active_zone())
    capability = SubmitDeliveryLocationCapability(
        DeliveryService(repository, 1), DisabledReverseGeocoder()
    )
    inbound_id = uuid4()
    context = ExecutionContext(
        tenant_id=UUID(int=1),
        conversation_id=uuid4(),
        channel=ChannelName.WHATSAPP,
        request_id="meta-whatsapp:wamid.location",
        channel_customer_id="+919999999999",
        inbound_message=TrustedInboundMessageContext(
            inbound_message_id=inbound_id,
            request_id="meta-whatsapp:wamid.location",
            message_kind=MessageKind.LOCATION,
            location=InboundLocation(latitude="28.612345", longitude="77.234567"),
        ),
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(
            stage=OnboardingStage.COLLECTING_LOCATION,
            delivery_input_mode=DeliveryInputMode.WHATSAPP_LOCATION,
            pending_customer_name="Samad",
            pending_phone_number="9999999999",
        )
    )
    output = await capability.execute(
        CapabilityInput(data={}, session=session, context=context)
    )
    pending = output.session.customer_onboarding.pending_delivery_location
    assert pending is not None
    assert pending.source_inbound_message_id == inbound_id
    assert repository.received == (
        UUID(int=1),
        Decimal("28.612345"),
        Decimal("77.234567"),
    )
    assert output.outcome.fragments[0].id == "delivery-location-serviceable"
    assert "28.612345" not in str(output.outcome)
    assert "77.234567" not in str(output.outcome)


@pytest.mark.asyncio
async def test_serviceability_distinguishes_outside_from_infrastructure_failure() -> (
    None
):
    outside = await DeliveryService(ZoneRepository(), 1).check_serviceability(
        UUID(int=1), Decimal(28), Decimal(77)
    )
    unavailable = await DeliveryService(
        ZoneRepository(fail=True), 1
    ).check_serviceability(UUID(int=1), Decimal(28), Decimal(77))
    assert outside.kind is ServiceabilityKind.OUTSIDE_SERVICE_AREA
    assert unavailable.kind is ServiceabilityKind.TEMPORARILY_UNAVAILABLE


@pytest.mark.asyncio
async def test_submit_location_rejects_llm_coordinate_arguments() -> None:
    capability = SubmitDeliveryLocationCapability(
        DeliveryService(ZoneRepository(active_zone()), 1), DisabledReverseGeocoder()
    )
    output = await capability.execute(
        CapabilityInput(
            data={"latitude": "28", "longitude": "77"},
            session=CommerceSession(),
            context=ExecutionContext(),
        )
    )
    assert output.outcome.fragments[0].id == "location-message-invalid"


@pytest.mark.asyncio
async def test_returning_customer_location_requires_explicit_save_or_temporary_choice() -> (
    None
):
    saved = SavedDetails()
    capability = SubmitDeliveryLocationCapability(
        DeliveryService(ZoneRepository(active_zone()), 1),
        DisabledReverseGeocoder(),
        saved,  # type: ignore[arg-type]
    )
    context = ExecutionContext(
        tenant_id=UUID(int=1),
        conversation_id=uuid4(),
        channel=ChannelName.WHATSAPP,
        channel_customer_id="+919999999999",
        request_id="meta-whatsapp:wamid.replace",
        inbound_message=TrustedInboundMessageContext(
            inbound_message_id=uuid4(),
            request_id="meta-whatsapp:wamid.replace",
            message_kind=MessageKind.LOCATION,
            location=InboundLocation(latitude="28.6", longitude="77.2"),
        ),
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(stage=OnboardingStage.COMPLETED)
    )
    output = await capability.execute(
        CapabilityInput(data={}, session=session, context=context)
    )
    assert output.session.customer_onboarding.stage is OnboardingStage.COMPLETED
    pending = output.session.pending_customer_location
    assert pending is not None
    assert pending.use is None
    assert output.outcome.follow_up is not None
    assert output.outcome.follow_up.id == "choose-customer-location-use"


@pytest.mark.asyncio
async def test_post_onboarding_location_can_be_selected_temporarily_without_saving() -> None:
    pending = PendingDeliveryLocation(
        latitude=Decimal("28.6"),
        longitude=Decimal("77.2"),
        zone_id=uuid4(),
        zone_name="Delhi East",
        zone_version=1,
        checked_at=datetime.now(timezone.utc),
        source_inbound_message_id=uuid4(),
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(stage=OnboardingStage.COMPLETED),
        pending_customer_location=PendingCustomerLocation(delivery_location=pending),
    )
    selected = await ChooseCustomerLocationUseCapability().execute(
        CapabilityInput(data={"save_address": False}, session=session, context=ExecutionContext())
    )
    completed = await CollectDeliveryAddressDetailsCapability(object()).execute(
        CapabilityInput(
            data={"address_details": "B-68, 2nd Floor"},
            session=selected.session,
            context=ExecutionContext(),
        )
    )

    retained = completed.session.pending_customer_location
    assert retained is not None
    assert retained.use is CustomerLocationUse.TEMPORARY
    assert retained.address_details == "B-68, 2nd Floor"
    assert completed.outcome.fragments[0].id == "temporary-delivery-address-ready"


@pytest.mark.asyncio
async def test_saving_post_onboarding_location_adds_non_default_address() -> None:
    saved = SavedDetails()
    pending = PendingDeliveryLocation(
        latitude=Decimal("28.6"),
        longitude=Decimal("77.2"),
        zone_id=uuid4(),
        zone_name="Delhi East",
        zone_version=1,
        checked_at=datetime.now(timezone.utc),
        source_inbound_message_id=uuid4(),
    )
    session = CommerceSession(
        customer_onboarding=CustomerOnboardingState(stage=OnboardingStage.COMPLETED),
        pending_customer_location=PendingCustomerLocation(delivery_location=pending),
    )
    context = ExecutionContext(
        tenant_id=UUID(int=1),
        channel=ChannelName.WHATSAPP,
        channel_customer_id="+919999999999",
    )
    selected = await ChooseCustomerLocationUseCapability().execute(
        CapabilityInput(data={"save_address": True}, session=session, context=context)
    )
    completed = await CollectDeliveryAddressDetailsCapability(
        object(), saved  # type: ignore[arg-type]
    ).execute(
        CapabilityInput(
            data={"address_details": "B-68, 2nd Floor"},
            session=selected.session,
            context=context,
        )
    )

    assert completed.session.pending_customer_location is not None
    assert len(saved.added) == 1
    assert saved.added[0][-1] == {"set_as_default": False}
