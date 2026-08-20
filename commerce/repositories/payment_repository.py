from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from commerce.models import (
    DeliveryLocationSnapshot,
    OnlinePaymentReady,
    Order,
    PaymentAttempt,
    StaleCheckout,
    StockUnavailable,
    VerifiedPaymentEvent,
)

PaymentCreationResult = OnlinePaymentReady | StockUnavailable | StaleCheckout


class PaymentRepository(ABC):
    @abstractmethod
    async def create_provisional_order(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        cart_id: UUID,
        expected_cart_version: int,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
        provider: str,
        expires_at: datetime,
        idempotency_key: str,
        delivery_location: DeliveryLocationSnapshot | None = None,
    ) -> PaymentCreationResult: ...

    @abstractmethod
    async def persist_provider_checkout(
        self,
        attempt_id: UUID,
        provider_payment_id: str,
        checkout_url: str,
        expires_at: datetime,
    ) -> OnlinePaymentReady: ...

    @abstractmethod
    async def fail_creation(self, attempt_id: UUID, failure_code: str) -> None: ...

    @abstractmethod
    async def get_attempt(self, attempt_id: UUID) -> PaymentAttempt: ...

    @abstractmethod
    async def get_latest_attempt(
        self, tenant_id: UUID, conversation_id: UUID, order_id: UUID | None = None
    ) -> PaymentAttempt | None: ...

    @abstractmethod
    async def create_retry_attempt(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        provider: str,
        expires_at: datetime,
        idempotency_key: str,
        order_id: UUID | None = None,
    ) -> OnlinePaymentReady | StockUnavailable: ...

    @abstractmethod
    async def switch_to_cod(
        self, tenant_id: UUID, conversation_id: UUID, order_id: UUID | None = None
    ) -> Order: ...

    @abstractmethod
    async def process_event(
        self, event: VerifiedPaymentEvent, payload_hash: str
    ) -> PaymentAttempt | None: ...

    @abstractmethod
    async def claim_reconciliation_batch(
        self, limit: int, now: datetime
    ) -> tuple[PaymentAttempt, ...]: ...
