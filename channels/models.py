from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from commerce.models import ChannelName, NotificationContentMode
from commerce.models.delivery_location import InboundLocation


class MessageKind(str, Enum):
    TEXT = "TEXT"
    LOCATION = "LOCATION"
    UNSUPPORTED = "UNSUPPORTED"


class WhatsAppProviderName(str, Enum):
    TWILIO = "twilio"
    META_CLOUD = "meta_cloud"


class InboundStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    RETRYABLE = "RETRYABLE"
    PROCESSED = "PROCESSED"
    DEAD_LETTER = "DEAD_LETTER"


class OutboundStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    RETRYABLE = "RETRYABLE"
    ACCEPTED = "ACCEPTED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"
    TEMPLATE_REQUIRED = "TEMPLATE_REQUIRED"
    AMBIGUOUS = "AMBIGUOUS"


class ChannelConversation(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tenant_id: UUID
    channel: ChannelName
    channel_customer_id: str
    conversation_id: UUID
    last_inbound_at: datetime
    created_at: datetime
    updated_at: datetime


class InboundMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tenant_id: UUID
    channel: ChannelName
    provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO
    provider_message_id: str
    conversation_id: UUID
    sender_id: str
    recipient_id: str
    body: str
    message_kind: MessageKind
    location: InboundLocation | None = None
    status: InboundStatus
    attempt_count: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    last_error_code: str | None
    received_at: datetime
    processed_at: datetime | None


class OutboundMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    tenant_id: UUID
    channel: ChannelName
    provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO
    conversation_id: UUID
    source_inbound_id: UUID | None = None
    recipient_id: str
    sender_id: str
    body: str | None = None
    content_mode: NotificationContentMode = NotificationContentMode.TEXT
    content_sid: str | None = None
    content_variables: dict[str, Any] | None = None
    template_key: str | None = None
    template_name: str | None = None
    template_language: str | None = None
    status: OutboundStatus
    attempt_count: int
    next_attempt_at: datetime
    lease_expires_at: datetime | None
    provider_message_id: str | None
    last_error_code: str | None
    created_at: datetime
    sent_at: datetime | None
    updated_at: datetime


class DeliveryEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    channel: ChannelName
    provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO
    provider_message_id: str
    status: OutboundStatus
    error_code: str | None
    provider_event_at: datetime | None = None
    received_at: datetime


class ProviderMessageResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider_message_id: str
    status: OutboundStatus = OutboundStatus.ACCEPTED


class ApprovedTemplateMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    name: str
    language: str | None = None
    parameters: dict[str, str]


@dataclass(frozen=True)
class NormalizedInboundEvent:
    provider_message_id: str
    sender_id: str
    recipient_id: str
    body: str
    message_kind: MessageKind
    location: InboundLocation | None = None


@dataclass(frozen=True)
class NormalizedDeliveryStatusEvent:
    provider_message_id: str
    status: OutboundStatus
    provider_event_at: datetime | None
    error_code: str | None


@dataclass(frozen=True)
class NormalizedWebhookBatch:
    inbound: tuple[NormalizedInboundEvent, ...]
    statuses: tuple[NormalizedDeliveryStatusEvent, ...]
    skipped: int = 0
