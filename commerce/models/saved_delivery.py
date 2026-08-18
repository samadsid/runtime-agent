from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChannelName(str, Enum):
    DEVELOPMENT_HTTP = "development_http"
    WHATSAPP = "whatsapp"


class OnboardingStatus(str, Enum):
    INCOMPLETE = "INCOMPLETE"
    COMPLETED = "COMPLETED"


class OnboardingStage(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_STARTED = "NOT_STARTED"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    REVIEWING_DETAILS = "REVIEWING_DETAILS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class ProfileField(str, Enum):
    CUSTOMER_NAME = "customer_name"
    PHONE_NUMBER = "phone_number"
    DELIVERY_ADDRESS = "delivery_address"


class CustomerOnboardingState(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: OnboardingStage = OnboardingStage.NOT_STARTED
    pending_customer_name: str | None = None
    pending_phone_number: str | None = None
    pending_delivery_address: str | None = None


class CustomerProfileProjection(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_available: bool = False
    onboarding_completed: bool = False
    preferred_name: str | None = None
    missing_fields: tuple[ProfileField, ...] = ()
    hydration_failed: bool = False
    has_stable_identity: bool = False


class SavedDeliveryProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    channel: ChannelName
    channel_customer_id: str
    customer_name: str | None = None
    phone_number: str | None = None
    phone_verified: bool = False
    onboarding_status: OnboardingStatus = OnboardingStatus.INCOMPLETE
    profile_consent_version: str | None = None
    profile_consented_at: datetime | None = None
    onboarding_request_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SavedDeliveryAddress(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    profile_id: UUID
    label: str
    delivery_address: str
    is_default: bool
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class SavedAddressOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    address_id: UUID
    label: str
    delivery_address: str
    is_default: bool
    version: int = Field(ge=1)


class PendingSavedProfileUse(BaseModel):
    """Exact saved values offered for optional checkout use."""

    model_config = ConfigDict(frozen=True)

    profile_id: UUID
    customer_name: str | None = None
    phone_number: str | None = None
    address_id: UUID | None = None
    delivery_address: str | None = None


class SavedDetailsConfirmationReason(str, Enum):
    CONSENT = "CONSENT"
    OVERWRITE = "OVERWRITE"


class PendingSavedDetailsSave(BaseModel):
    """Short-lived proposal awaiting explicit save or overwrite approval."""

    model_config = ConfigDict(frozen=True)

    reason: SavedDetailsConfirmationReason
    customer_name: str | None = None
    phone_number: str | None = None
    address_label: str | None = None
    delivery_address: str | None = None
    set_as_default: bool = False
    profile_existed: bool = False
    expected_customer_name: str | None = None
    expected_phone_number: str | None = None
