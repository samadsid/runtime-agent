from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from channels.models import MessageKind
from commerce.models import (
    ChannelName,
    CommerceSession,
    CustomerOnboardingState,
    DeliveryZone,
    DeliveryZoneStatus,
    InboundLocation,
    OnboardingStage,
    OnboardingStatus,
    SavedDeliveryAddress,
    SavedDeliveryProfile,
    ServiceabilityKind,
)
from commerce.repositories import DeliveryZoneRepository
from commerce.services import DeliveryService, DisabledReverseGeocoder
from runtime.capabilities import CapabilityInput, ExecutionContext
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

    async def list_addresses(self, tenant_id, channel, customer_id):
        return self.profile, (self.address,)


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
            stage=OnboardingStage.COLLECTING_DETAILS,
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
async def test_returning_customer_location_starts_version_bound_replacement_review() -> (
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
    proposal = output.session.customer_onboarding
    assert proposal.stage is OnboardingStage.COLLECTING_DETAILS
    assert proposal.replacement_address_id == saved.address.id
    assert proposal.replacement_address_version == 4
    assert proposal.pending_delivery_address is None
