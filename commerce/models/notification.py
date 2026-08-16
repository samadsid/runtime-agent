from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .saved_delivery import ChannelName


class NotificationType(str, Enum):
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_PREPARING = "ORDER_PREPARING"
    ORDER_OUT_FOR_DELIVERY = "ORDER_OUT_FOR_DELIVERY"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"


class NotificationSourceType(str, Enum):
    ORDER_STATUS_HISTORY = "ORDER_STATUS_HISTORY"
    PAYMENT_EVENT = "PAYMENT_EVENT"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    RETRYABLE = "RETRYABLE"
    DISPATCHED = "DISPATCHED"
    DEAD_LETTER = "DEAD_LETTER"
    SUPPRESSED = "SUPPRESSED"


class NotificationSuppressionReason(str, Enum):
    NO_SUPPORTED_CHANNEL = "no_supported_channel"
    WEB_PUSH_NOT_SUPPORTED = "web_push_not_supported"
    PRE_FEATURE_HISTORY = "pre_feature_history"


class NotificationContentMode(str, Enum):
    TEXT = "TEXT"
    TEMPLATE = "TEMPLATE"


class OrderNotificationPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: int = 1
    order_reference: str
    order_status: str
    payment_method: str
    currency: str
    total_amount: str
    occurred_at: datetime


class NotificationEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    notification_type: NotificationType
    source_type: NotificationSourceType
    source_id: UUID
    order_id: UUID | None = None
    customer_channel_id: UUID | None = None
    preferred_channel: ChannelName | None = None
    locale: str | None = None
    payload: dict[str, Any]
    payload_version: int = 1
    status: NotificationStatus
    attempt_count: int = Field(ge=0)
    available_at: datetime
    lease_expires_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime
    processed_at: datetime | None = None

    def order_payload(self) -> OrderNotificationPayload:
        if self.source_type != NotificationSourceType.ORDER_STATUS_HISTORY:
            raise ValueError("Notification does not contain an order payload.")
        payload = OrderNotificationPayload.model_validate(self.payload)
        if payload.version != self.payload_version:
            raise ValueError(
                "Notification payload version does not match its envelope."
            )
        return payload


class NotificationDelivery(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    notification_id: UUID
    channel: ChannelName
    channel_outbound_message_id: UUID
    template_key: str
    template_version: int = Field(ge=1)
    created_at: datetime


class NotificationTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    version: int = Field(ge=1)
    notification_type: NotificationType
    channel: ChannelName
    locale: str
    body_template: str
    provider_content_sid: str | None = None
    provider_variables: tuple[str, ...] = ()
