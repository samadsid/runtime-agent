from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChannelName(str, Enum):
    DEVELOPMENT_HTTP = "development_http"
    TWILIO_WHATSAPP = "twilio_whatsapp"


class SavedDeliveryProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    channel: ChannelName
    channel_customer_id: str
    customer_name: str | None = None
    phone_number: str | None = None
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
    """Exact profile values offered for optional checkout use."""

    model_config = ConfigDict(frozen=True)

    profile_id: UUID
    customer_name: str | None = None
    phone_number: str | None = None


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
