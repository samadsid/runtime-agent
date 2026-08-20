from __future__ import annotations

from datetime import datetime
from uuid import UUID

from commerce.models import (
    ChannelName,
    CustomerProfileProjection,
    DeliveryLocationSnapshot,
    OnboardingStatus,
    ProfileField,
    SavedDeliveryAddress,
    SavedDeliveryProfile,
)
from commerce.repositories import SavedDeliveryDetailsRepository

from .phone_validation import PhoneValidationPolicy


class InvalidSavedDeliveryDetailsError(ValueError):
    pass


class GuestSavedDeliveryDetailsError(PermissionError):
    pass


class SavedDeliveryDetailsService:
    ONBOARDING_CONSENT_VERSION = "saved-delivery-profile/v1"
    ONBOARDING_ADDRESS_LABEL = "Home"

    def __init__(
        self,
        repository: SavedDeliveryDetailsRepository,
        phone_policy: PhoneValidationPolicy,
    ) -> None:
        self._repository = repository
        self._phone_policy = phone_policy

    async def get_profile(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str | None,
    ) -> SavedDeliveryProfile | None:
        if channel_customer_id is None:
            return None
        return await self._repository.get_profile(
            tenant_id, channel, channel_customer_id
        )

    async def get_profile_projection(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str | None,
    ) -> CustomerProfileProjection:
        if channel_customer_id is None:
            return CustomerProfileProjection()
        profile = await self.get_profile(tenant_id, channel, channel_customer_id)
        if profile is None:
            return CustomerProfileProjection(
                missing_fields=(
                    ProfileField.CUSTOMER_NAME,
                    ProfileField.PHONE_NUMBER,
                    ProfileField.DELIVERY_ADDRESS,
                )
            )
        addresses = await self._repository.list_addresses(tenant_id, profile.id)
        missing: list[ProfileField] = []
        if profile.customer_name is None:
            missing.append(ProfileField.CUSTOMER_NAME)
        if profile.phone_number is None:
            missing.append(ProfileField.PHONE_NUMBER)
        if not addresses:
            missing.append(ProfileField.DELIVERY_ADDRESS)
        completed = (
            profile.onboarding_status is OnboardingStatus.COMPLETED
            and profile.profile_consent_version is not None
            and profile.profile_consented_at is not None
            and not missing
        )
        return CustomerProfileProjection(
            profile_available=True,
            onboarding_completed=completed,
            preferred_name=profile.customer_name,
            missing_fields=tuple(missing),
        )

    async def get_onboarding_values(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        profile, addresses = await self.list_addresses(
            tenant_id, channel, channel_customer_id
        )
        default = next((item for item in addresses if item.is_default), None)
        address = default or (addresses[0] if addresses else None)
        return (
            profile.customer_name if profile else None,
            profile.phone_number if profile else None,
            address.delivery_address if address else None,
        )

    async def complete_onboarding(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str | None,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
        consented_at: datetime,
        request_id: str | None,
        delivery_location: DeliveryLocationSnapshot | None = None,
    ) -> SavedDeliveryProfile:
        customer_id = self._require_customer(channel_customer_id)
        if request_id is None or not request_id.strip():
            raise InvalidSavedDeliveryDetailsError("A trusted request ID is required.")
        name, phone, _, address = self.validate_details(
            customer_name,
            phone_number,
            self.ONBOARDING_ADDRESS_LABEL,
            delivery_address,
        )
        assert name is not None and phone is not None and address is not None
        return await self._repository.complete_onboarding(
            tenant_id,
            channel,
            customer_id,
            name,
            phone,
            address,
            self.ONBOARDING_CONSENT_VERSION,
            consented_at,
            request_id,
            self.ONBOARDING_ADDRESS_LABEL,
            delivery_location,
        )

    async def list_addresses(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str | None,
    ) -> tuple[SavedDeliveryProfile | None, tuple[SavedDeliveryAddress, ...]]:
        profile = await self.get_profile(tenant_id, channel, channel_customer_id)
        if profile is None:
            return None, ()
        return profile, await self._repository.list_addresses(tenant_id, profile.id)

    async def get_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        address_id: UUID,
    ) -> SavedDeliveryAddress | None:
        return await self._repository.get_address(tenant_id, profile_id, address_id)

    async def save_details(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str | None,
        customer_name: str | None,
        phone_number: str | None,
        address_label: str | None,
        delivery_address: str | None,
        set_as_default: bool,
        expected_profile_values: tuple[str | None, str | None] | None = None,
        expect_profile_absent: bool = False,
    ) -> tuple[SavedDeliveryProfile, SavedDeliveryAddress | None]:
        customer_id = self._require_customer(channel_customer_id)
        (
            customer_name,
            phone_number,
            address_label,
            delivery_address,
        ) = self.validate_details(
            customer_name, phone_number, address_label, delivery_address
        )
        return await self._repository.save_details(
            tenant_id,
            channel,
            customer_id,
            customer_name,
            phone_number,
            address_label,
            delivery_address,
            set_as_default,
            expected_profile_values,
            expect_profile_absent,
        )

    def validate_details(
        self,
        customer_name: str | None,
        phone_number: str | None,
        address_label: str | None,
        delivery_address: str | None,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        customer_name = self._optional_text(customer_name, "customer name")
        phone_number = self._optional_text(phone_number, "phone number")
        address_label = self._optional_text(address_label, "address label")
        delivery_address = self._optional_text(delivery_address, "delivery address")
        if phone_number is not None and not self._phone_policy.is_valid(phone_number):
            raise InvalidSavedDeliveryDetailsError("Invalid phone number.")
        if (address_label is None) != (delivery_address is None):
            raise InvalidSavedDeliveryDetailsError(
                "An address label and delivery address are both required."
            )
        if not any((customer_name, phone_number, delivery_address)):
            raise InvalidSavedDeliveryDetailsError("No delivery details were supplied.")
        return customer_name, phone_number, address_label, delivery_address

    async def update_address(
        self,
        tenant_id: UUID,
        channel_customer_id: str | None,
        profile_id: UUID,
        address_id: UUID,
        expected_version: int,
        label: str | None,
        delivery_address: str | None,
        delivery_location: DeliveryLocationSnapshot | None = None,
    ) -> SavedDeliveryAddress:
        self._require_customer(channel_customer_id)
        label = self._optional_text(label, "address label")
        delivery_address = self._optional_text(delivery_address, "delivery address")
        if label is None and delivery_address is None and delivery_location is None:
            raise InvalidSavedDeliveryDetailsError("No address change was supplied.")
        if delivery_location is None:
            return await self._repository.update_address(
                tenant_id,
                profile_id,
                address_id,
                expected_version,
                label,
                delivery_address,
            )
        return await self._repository.update_address(
            tenant_id,
            profile_id,
            address_id,
            expected_version,
            label,
            delivery_address,
            delivery_location,
        )

    async def delete_address(
        self,
        tenant_id: UUID,
        channel_customer_id: str | None,
        profile_id: UUID,
        address_id: UUID,
        expected_version: int,
    ) -> None:
        self._require_customer(channel_customer_id)
        await self._repository.delete_address(
            tenant_id, profile_id, address_id, expected_version
        )

    async def set_default_address(
        self,
        tenant_id: UUID,
        channel_customer_id: str | None,
        profile_id: UUID,
        address_id: UUID,
    ) -> SavedDeliveryAddress:
        self._require_customer(channel_customer_id)
        return await self._repository.set_default_address(
            tenant_id, profile_id, address_id
        )

    @staticmethod
    def _require_customer(channel_customer_id: str | None) -> str:
        if channel_customer_id is None:
            raise GuestSavedDeliveryDetailsError(
                "Saved delivery details are unavailable in guest mode."
            )
        value = channel_customer_id.strip()
        if not value:
            raise GuestSavedDeliveryDetailsError(
                "Saved delivery details are unavailable in guest mode."
            )
        return value

    @staticmethod
    def _optional_text(value: str | None, field: str) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise InvalidSavedDeliveryDetailsError(f"Invalid {field}.")
        return normalized
