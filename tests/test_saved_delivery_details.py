from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from commerce.models import (
    ChannelName,
    CheckoutStage,
    CheckoutState,
    CommerceSession,
    PendingSavedDetailsSave,
    SavedDeliveryAddress,
    SavedDeliveryProfile,
    SavedDetailsConfirmationReason,
)
from commerce.repositories import (
    SavedDeliveryAddressNotFoundError,
    SavedDeliveryDetailsRepository,
    SavedDeliveryProfileConflictError,
    StaleSavedDeliveryAddressError,
)
from commerce.services import NonEmptyPhoneValidationPolicy, SavedDeliveryDetailsService
from runtime.capabilities import CapabilityInput, ExecutionContext
from runtime.capabilities.confirm_save_delivery_details import (
    ConfirmSaveDeliveryDetailsCapability,
)
from runtime.capabilities.confirm_saved_profile_use import (
    ConfirmSavedProfileUseCapability,
)
from runtime.capabilities.list_saved_addresses import ListSavedAddressesCapability
from runtime.capabilities.save_delivery_details import SaveDeliveryDetailsCapability
from runtime.capabilities.select_saved_address import SelectSavedAddressCapability
from runtime.capabilities.update_saved_address import UpdateSavedAddressCapability
from runtime.capabilities.view_saved_delivery_profile import (
    ViewSavedDeliveryProfileCapability,
)
from runtime.contracts import ExecutionStatus
from runtime.graph.memory import GraphCheckpointer
from runtime.prompts.renderers import CommerceSessionRenderer


class FakeSavedDeliveryRepository(SavedDeliveryDetailsRepository):
    def __init__(self) -> None:
        self.profiles: dict[tuple[UUID, ChannelName, str], SavedDeliveryProfile] = {}
        self.addresses: dict[UUID, list[SavedDeliveryAddress]] = {}

    async def get_profile(self, tenant_id, channel, channel_customer_id):
        return self.profiles.get((tenant_id, channel, channel_customer_id))

    async def save_profile_details(
        self, tenant_id, channel, channel_customer_id, customer_name, phone_number
    ):
        profile, _ = await self.save_details(
            tenant_id,
            channel,
            channel_customer_id,
            customer_name,
            phone_number,
            None,
            None,
            False,
        )
        return profile

    async def save_details(
        self,
        tenant_id,
        channel,
        channel_customer_id,
        customer_name,
        phone_number,
        address_label,
        delivery_address,
        set_as_default,
        expected_profile_values=None,
        expect_profile_absent=False,
    ):
        key = (tenant_id, channel, channel_customer_id)
        current = self.profiles.get(key)
        if (
            expect_profile_absent
            and current is not None
            and (
                (
                    customer_name is not None
                    and current.customer_name not in {None, customer_name}
                )
                or (
                    phone_number is not None
                    and current.phone_number not in {None, phone_number}
                )
            )
        ):
            raise SavedDeliveryProfileConflictError()
        if (
            expected_profile_values is not None
            and current is not None
            and (current.customer_name, current.phone_number) != expected_profile_values
        ):
            raise SavedDeliveryProfileConflictError()
        now = datetime.now(timezone.utc)
        profile = SavedDeliveryProfile(
            id=current.id if current else uuid4(),
            tenant_id=tenant_id,
            channel=channel,
            channel_customer_id=channel_customer_id,
            customer_name=customer_name
            if customer_name is not None
            else (current.customer_name if current else None),
            phone_number=phone_number
            if phone_number is not None
            else (current.phone_number if current else None),
            created_at=current.created_at if current else now,
            updated_at=now,
        )
        self.profiles[key] = profile
        address = None
        if address_label is not None and delivery_address is not None:
            address = await self.add_address(
                tenant_id, profile.id, address_label, delivery_address, set_as_default
            )
        return profile, address

    async def list_addresses(self, tenant_id, profile_id):
        if not any(
            p.id == profile_id and p.tenant_id == tenant_id
            for p in self.profiles.values()
        ):
            return ()
        return tuple(
            sorted(
                self.addresses.get(profile_id, []),
                key=lambda a: (not a.is_default, a.created_at, str(a.id)),
            )
        )

    async def get_address(self, tenant_id, profile_id, address_id):
        values = await self.list_addresses(tenant_id, profile_id)
        return next((value for value in values if value.id == address_id), None)

    async def add_address(
        self, tenant_id, profile_id, label, delivery_address, set_as_default
    ):
        now = datetime.now(timezone.utc)
        values = self.addresses.setdefault(profile_id, [])
        if set_as_default:
            values[:] = [
                value.model_copy(
                    update={"is_default": False, "version": value.version + 1}
                )
                for value in values
            ]
        address = SavedDeliveryAddress(
            id=uuid4(),
            profile_id=profile_id,
            label=label,
            delivery_address=delivery_address,
            is_default=set_as_default,
            version=1,
            created_at=now,
            updated_at=now,
        )
        values.append(address)
        return address

    async def update_address(
        self,
        tenant_id,
        profile_id,
        address_id,
        expected_version,
        label,
        delivery_address,
    ):
        current = await self.get_address(tenant_id, profile_id, address_id)
        if current is None:
            raise SavedDeliveryAddressNotFoundError()
        if current.version != expected_version:
            raise StaleSavedDeliveryAddressError()
        updated = current.model_copy(
            update={
                "label": label or current.label,
                "delivery_address": delivery_address or current.delivery_address,
                "version": current.version + 1,
            }
        )
        values = self.addresses[profile_id]
        values[values.index(current)] = updated
        return updated

    async def delete_address(self, tenant_id, profile_id, address_id, expected_version):
        current = await self.get_address(tenant_id, profile_id, address_id)
        if current is None:
            raise SavedDeliveryAddressNotFoundError()
        if current.version != expected_version:
            raise StaleSavedDeliveryAddressError()
        self.addresses[profile_id].remove(current)

    async def set_default_address(self, tenant_id, profile_id, address_id):
        current = await self.get_address(tenant_id, profile_id, address_id)
        if current is None:
            raise SavedDeliveryAddressNotFoundError()
        values = self.addresses[profile_id]
        values[:] = [
            value.model_copy(update={"is_default": value.id == address_id})
            for value in values
        ]
        return next(value for value in values if value.id == address_id)


@pytest.fixture
def saved_fixture():
    repository = FakeSavedDeliveryRepository()
    service = SavedDeliveryDetailsService(repository, NonEmptyPhoneValidationPolicy())
    context = ExecutionContext(
        tenant_id=uuid4(),
        conversation_id=uuid4(),
        channel=ChannelName.DEVELOPMENT_HTTP,
        channel_customer_id="customer-1",
    )
    return repository, service, context


def capability_input(session, context, data=None):
    return CapabilityInput[CommerceSession](
        session=session, context=context, data=data or {}
    )


@pytest.mark.asyncio
async def test_guest_cannot_list_or_persist_saved_details(saved_fixture) -> None:
    _, service, context = saved_fixture
    guest = context.model_copy(update={"channel_customer_id": None})
    listed = await ListSavedAddressesCapability(service).execute(
        capability_input(CommerceSession(), guest)
    )
    saved = await SaveDeliveryDetailsCapability(service).execute(
        capability_input(
            CommerceSession(), guest, {"customer_name": "Sam", "consent": True}
        )
    )
    assert listed.outcome.status == ExecutionStatus.NOT_FOUND
    assert saved.outcome.fragments[0].id == "saved-addresses-unavailable-for-guest"


@pytest.mark.asyncio
async def test_explicit_consent_saves_and_lists_default_first(saved_fixture) -> None:
    _, service, context = saved_fixture
    capability = SaveDeliveryDetailsCapability(service)
    await capability.execute(
        capability_input(
            CommerceSession(),
            context,
            {
                "customer_name": "Sam",
                "phone_number": "9999",
                "address_label": "Office",
                "delivery_address": "2 Work Road",
                "consent": True,
            },
        )
    )
    result = await capability.execute(
        capability_input(
            CommerceSession(),
            context,
            {
                "address_label": "Home",
                "delivery_address": "1 Home Road",
                "set_as_default": True,
                "consent": True,
            },
        )
    )
    listed = await ListSavedAddressesCapability(service).execute(
        capability_input(result.session, context)
    )
    assert listed.outcome.status == ExecutionStatus.SUCCESS
    assert [option.label for option in listed.session.recent_saved_addresses] == [
        "Home",
        "Office",
    ]


@pytest.mark.asyncio
async def test_view_saved_profile_returns_persisted_phone_and_all_details(
    saved_fixture,
) -> None:
    _, service, context = saved_fixture
    await service.save_details(
        context.tenant_id,
        context.channel,
        context.channel_customer_id,
        "Samad",
        "9560717170",
        "Home",
        "B-68 New Zafrabad",
        True,
    )
    capability = ViewSavedDeliveryProfileCapability(service)

    phone = await capability.execute(
        capability_input(CommerceSession(), context, {"field": "phone_number"})
    )
    all_details = await capability.execute(
        capability_input(CommerceSession(), context, {"field": "all"})
    )

    assert phone.outcome.fragments[0].text == "Saved phone number: 9560717170"
    assert phone.outcome.protected_values == ("9560717170",)
    assert [fragment.id for fragment in all_details.outcome.fragments] == [
        "saved-customer-name",
        "saved-customer-phone",
        "saved-profile-address-1",
    ]


@pytest.mark.asyncio
async def test_profile_overwrite_requires_second_turn(saved_fixture) -> None:
    repository, service, context = saved_fixture
    save = SaveDeliveryDetailsCapability(service)
    first = await save.execute(
        capability_input(
            CommerceSession(), context, {"customer_name": "Sam", "consent": True}
        )
    )
    proposed = await save.execute(
        capability_input(
            first.session, context, {"customer_name": "Aman", "consent": True}
        )
    )
    profile = await service.get_profile(
        context.tenant_id, context.channel, context.channel_customer_id
    )
    assert profile is not None and profile.customer_name == "Sam"
    assert proposed.outcome.fragments[0].id == "saved-details-differ"
    confirmed = await ConfirmSaveDeliveryDetailsCapability(service).execute(
        capability_input(proposed.session, context, {"confirmed": True})
    )
    profile = next(iter(repository.profiles.values()))
    assert confirmed.outcome.status == ExecutionStatus.SUCCESS
    assert profile.customer_name == "Aman"


@pytest.mark.asyncio
async def test_select_copies_snapshot_and_saved_update_does_not_change_checkout(
    saved_fixture,
) -> None:
    _, service, context = saved_fixture
    saved = await SaveDeliveryDetailsCapability(service).execute(
        capability_input(
            CommerceSession(),
            context,
            {
                "customer_name": "Sam",
                "phone_number": "12345678",
                "address_label": "Home",
                "delivery_address": "Old Road",
                "consent": True,
            },
        )
    )
    listed = await ListSavedAddressesCapability(service).execute(
        capability_input(saved.session, context)
    )
    checkout = CheckoutState(
        stage=CheckoutStage.COLLECTING_DETAILS,
        source_cart_id=uuid4(),
        source_cart_version=1,
    )
    selected = await SelectSavedAddressCapability(service).execute(
        capability_input(
            listed.session.model_copy(update={"checkout": checkout}),
            context,
            {"ordinal": 1},
        )
    )
    accepted = await ConfirmSavedProfileUseCapability(service).execute(
        capability_input(selected.session, context, {"confirmed": True})
    )
    assert accepted.session.checkout.delivery_address == "Old Road"
    updated = await UpdateSavedAddressCapability(service).execute(
        capability_input(
            selected.session, context, {"ordinal": 1, "delivery_address": "New Road"}
        )
    )
    assert updated.session.checkout.delivery_address == "Old Road"


def test_planner_projection_hides_saved_address_text_and_identifiers() -> None:
    address_id = uuid4()
    from commerce.models import SavedAddressOption

    rendered = CommerceSessionRenderer().render(
        CommerceSession(
            recent_saved_addresses=(
                SavedAddressOption(
                    address_id=address_id,
                    label="Home",
                    delivery_address="Secret Road",
                    is_default=True,
                    version=1,
                ),
            )
        )
    )
    assert "1. Home — default" in rendered
    assert "Secret Road" not in rendered
    assert str(address_id) not in rendered


def test_saved_delivery_pending_state_round_trips_through_checkpoint_serializer() -> (
    None
):
    session = CommerceSession(
        pending_saved_details_save=PendingSavedDetailsSave(
            reason=SavedDetailsConfirmationReason.OVERWRITE,
            customer_name="Sam",
            expected_customer_name="Aman",
            profile_existed=True,
        )
    )
    serializer = GraphCheckpointer().instance.serde
    restored = serializer.loads_typed(serializer.dumps_typed(session))
    assert restored == session
