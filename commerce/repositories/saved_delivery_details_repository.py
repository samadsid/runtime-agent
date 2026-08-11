from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from commerce.models import ChannelName, SavedDeliveryAddress, SavedDeliveryProfile


class SavedDeliveryDetailsRepository(ABC):
    @abstractmethod
    async def get_profile(
        self, tenant_id: UUID, channel: ChannelName, channel_customer_id: str
    ) -> SavedDeliveryProfile | None: ...

    @abstractmethod
    async def save_profile_details(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str,
        customer_name: str | None,
        phone_number: str | None,
    ) -> SavedDeliveryProfile: ...

    @abstractmethod
    async def save_details(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str,
        customer_name: str | None,
        phone_number: str | None,
        address_label: str | None,
        delivery_address: str | None,
        set_as_default: bool,
        expected_profile_values: tuple[str | None, str | None] | None = None,
        expect_profile_absent: bool = False,
    ) -> tuple[SavedDeliveryProfile, SavedDeliveryAddress | None]: ...

    @abstractmethod
    async def list_addresses(
        self, tenant_id: UUID, profile_id: UUID
    ) -> tuple[SavedDeliveryAddress, ...]: ...

    @abstractmethod
    async def get_address(
        self, tenant_id: UUID, profile_id: UUID, address_id: UUID
    ) -> SavedDeliveryAddress | None: ...

    @abstractmethod
    async def add_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        label: str,
        delivery_address: str,
        set_as_default: bool,
    ) -> SavedDeliveryAddress: ...

    @abstractmethod
    async def update_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        address_id: UUID,
        expected_version: int,
        label: str | None,
        delivery_address: str | None,
    ) -> SavedDeliveryAddress: ...

    @abstractmethod
    async def delete_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        address_id: UUID,
        expected_version: int,
    ) -> None: ...

    @abstractmethod
    async def set_default_address(
        self, tenant_id: UUID, profile_id: UUID, address_id: UUID
    ) -> SavedDeliveryAddress: ...


class SavedDeliveryDetailsError(RuntimeError):
    pass


class SavedDeliveryProfileConflictError(SavedDeliveryDetailsError):
    pass


class SavedDeliveryAddressNotFoundError(SavedDeliveryDetailsError):
    pass


class StaleSavedDeliveryAddressError(SavedDeliveryDetailsError):
    pass


class SavedDeliveryPersistenceError(SavedDeliveryDetailsError):
    pass
