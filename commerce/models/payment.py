from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .order import Order


class PaymentAttemptStatus(str, Enum):
    CREATING = "CREATING"
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class WebhookProcessingStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    RETRYABLE = "RETRYABLE"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


class ProviderPaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class PaymentAttempt(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    order_id: UUID
    provider: str
    provider_payment_id: str | None = None
    idempotency_key: str
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str
    status: PaymentAttemptStatus
    checkout_url: str | None = None
    expires_at: datetime
    failure_code: str | None = None
    created_at: datetime
    updated_at: datetime


class PaymentWebhookEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    provider: str
    provider_event_id: str
    provider_payment_id: str
    event_type: str
    payload_hash: str
    processing_status: WebhookProcessingStatus
    received_at: datetime
    processed_at: datetime | None = None
    failure_reason: str | None = None


class CreateProviderCheckoutRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    merchant_reference: str
    idempotency_key: str
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str
    expires_at: datetime
    return_url: str


class ProviderCheckout(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_payment_id: str
    status: ProviderPaymentStatus
    checkout_url: str
    expires_at: datetime


class VerifiedPaymentEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    provider_event_id: str
    provider_payment_id: str
    status: ProviderPaymentStatus
    amount: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str
    occurred_at: datetime


class OnlinePaymentReady(BaseModel):
    model_config = ConfigDict(frozen=True)

    order: Order
    attempt: PaymentAttempt
    idempotent: bool = False


OnlinePaymentReady.model_rebuild()
