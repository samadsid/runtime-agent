from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeliveryZoneStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class SavedAddressServiceabilityStatus(str, Enum):
    SERVICEABLE = "SERVICEABLE"
    REVALIDATION_REQUIRED = "REVALIDATION_REQUIRED"
    LEGACY_UNVALIDATED = "LEGACY_UNVALIDATED"


class ServiceabilityKind(str, Enum):
    SERVICEABLE = "SERVICEABLE"
    OUTSIDE_SERVICE_AREA = "OUTSIDE_SERVICE_AREA"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"


class InboundLocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    latitude: Decimal = Field(ge=Decimal(-90), le=Decimal(90), allow_inf_nan=False)
    longitude: Decimal = Field(ge=Decimal(-180), le=Decimal(180), allow_inf_nan=False)
    name: str | None = Field(default=None, max_length=200)
    provider_address: str | None = Field(default=None, max_length=500)

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def reject_boolean_coordinates(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Boolean coordinates are invalid.")  # noqa: TRY004
        return value

    @field_validator("name", "provider_address", mode="before")
    @classmethod
    def normalize_provider_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Provider location text must be a string.")  # noqa: TRY004
        normalized = " ".join(value.split())
        return normalized or None


class DeliveryZone(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=120)
    status: DeliveryZoneStatus
    priority: int = Field(ge=0)
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    boundary: dict[str, object] | None = None


class ServiceabilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ServiceabilityKind
    zone_id: UUID | None = None
    zone_name: str | None = None
    zone_version: int | None = Field(default=None, ge=1)
    checked_at: datetime


class DeliveryLocationSnapshot(BaseModel):
    """Canonical exact destination projection reused by pending, saved and order state."""

    model_config = ConfigDict(frozen=True)

    latitude: Decimal = Field(ge=Decimal(-90), le=Decimal(90), allow_inf_nan=False)
    longitude: Decimal = Field(ge=Decimal(-180), le=Decimal(180), allow_inf_nan=False)
    zone_id: UUID
    zone_name: str = Field(min_length=1, max_length=120)
    zone_version: int = Field(ge=1)
    formatted_area: str | None = Field(default=None, max_length=500)
    address_details: str | None = Field(default=None, max_length=500)
    checked_at: datetime
    source_inbound_message_id: UUID | None = None


class PendingDeliveryLocation(DeliveryLocationSnapshot):
    source_inbound_message_id: UUID


class ReverseGeocodeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    formatted_area: str | None = None
    locality: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    provider_reference: str | None = None
