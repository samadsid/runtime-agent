from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from commerce.models import (
    CreateProviderCheckoutRequest,
    OnlinePaymentReady,
    PaymentAttemptStatus,
    ProviderPaymentStatus,
)
from commerce.payments import (
    PaymentProvider,
    PaymentProviderConfigurationError,
    PaymentProviderInvalidResponseError,
    PaymentProviderTemporaryError,
)
from commerce.repositories import PaymentRepository


class PaymentService:
    def __init__(
        self,
        repository: PaymentRepository,
        provider: PaymentProvider,
        ttl_minutes: int,
        return_url: str,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._ttl = timedelta(minutes=ttl_minutes)
        self._return_url = return_url

    async def start_online_payment(self, **values):
        expires_at = datetime.now(timezone.utc) + self._ttl
        result = await self._repository.create_provisional_order(
            **values,
            provider=self._provider.name,
            expires_at=expires_at,
            idempotency_key=uuid4().hex,
        )
        if (
            not isinstance(result, OnlinePaymentReady)
            or result.attempt.status != PaymentAttemptStatus.CREATING
        ):
            return result
        return await self._create_provider_checkout(result)

    async def retry_online_payment(
        self, tenant_id: UUID, conversation_id: UUID, order_id: UUID | None = None
    ):
        expires_at = datetime.now(timezone.utc) + self._ttl
        result = await self._repository.create_retry_attempt(
            tenant_id,
            conversation_id,
            self._provider.name,
            expires_at,
            uuid4().hex,
            order_id,
        )
        if (
            not isinstance(result, OnlinePaymentReady)
            or result.attempt.status != PaymentAttemptStatus.CREATING
        ):
            return result
        return await self._create_provider_checkout(result)

    async def _create_provider_checkout(self, ready: OnlinePaymentReady):
        attempt = ready.attempt
        try:
            checkout = await self._provider.create_checkout(
                CreateProviderCheckoutRequest(
                    merchant_reference=str(ready.order.id),
                    idempotency_key=attempt.idempotency_key,
                    amount=attempt.amount,
                    currency=attempt.currency,
                    expires_at=attempt.expires_at,
                    return_url=self._return_url,
                )
            )
        except PaymentProviderTemporaryError:
            return ready
        except (PaymentProviderConfigurationError, PaymentProviderInvalidResponseError):
            await self._repository.fail_creation(attempt.id, "provider_creation_failed")
            return OnlinePaymentReady(
                order=ready.order,
                attempt=await self._repository.get_attempt(attempt.id),
            )
        return await self._repository.persist_provider_checkout(
            attempt.id,
            checkout.provider_payment_id,
            checkout.checkout_url,
            checkout.expires_at,
        )

    async def get_status(
        self, tenant_id: UUID, conversation_id: UUID, order_id: UUID | None = None
    ):
        return await self._repository.get_latest_attempt(
            tenant_id, conversation_id, order_id
        )

    async def switch_to_cod(
        self, tenant_id: UUID, conversation_id: UUID, order_id: UUID | None = None
    ):
        attempt = await self._repository.get_latest_attempt(
            tenant_id, conversation_id, order_id
        )
        if (
            attempt
            and attempt.status == PaymentAttemptStatus.CREATING
            and attempt.provider_payment_id
        ):
            status = await self._provider.get_payment_status(
                attempt.provider_payment_id
            )
            if status == ProviderPaymentStatus.SUCCEEDED:
                raise ValueError("Payment has already succeeded.")
        return await self._repository.switch_to_cod(
            tenant_id, conversation_id, order_id
        )

    async def reconcile_creating(self, attempt):
        """Replay provider creation with the original key; provider idempotency prevents duplication."""
        checkout = await self._provider.create_checkout(
            CreateProviderCheckoutRequest(
                merchant_reference=str(attempt.order_id),
                idempotency_key=attempt.idempotency_key,
                amount=attempt.amount,
                currency=attempt.currency,
                expires_at=attempt.expires_at,
                return_url=self._return_url,
            )
        )
        return await self._repository.persist_provider_checkout(
            attempt.id,
            checkout.provider_payment_id,
            checkout.checkout_url,
            checkout.expires_at,
        )
