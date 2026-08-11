from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

from commerce.models import ProviderPaymentStatus, VerifiedPaymentEvent
from commerce.payments import PaymentProvider
from commerce.repositories import PaymentRepository
from commerce.services.payment_event_service import PaymentEventService
from commerce.services.payment_service import PaymentService

logger = logging.getLogger(__name__)


class PaymentReconciliationJob:
    def __init__(
        self,
        repository: PaymentRepository,
        provider: PaymentProvider,
        event_service: PaymentEventService,
        payment_service: PaymentService,
        batch_size: int,
        interval_seconds: int,
    ) -> None:
        self._repository = repository
        self._provider = provider
        self._event_service = event_service
        self._payment_service = payment_service
        self._batch_size = batch_size
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run_once(self) -> None:
        now = datetime.now(timezone.utc)
        attempts = await self._repository.claim_reconciliation_batch(
            self._batch_size, now
        )
        for attempt in attempts:
            if not attempt.provider_payment_id:
                await self._payment_service.reconcile_creating(attempt)
                continue
            status = await self._provider.get_payment_status(
                attempt.provider_payment_id
            )
            if status == ProviderPaymentStatus.PENDING and attempt.expires_at <= now:
                status = ProviderPaymentStatus.EXPIRED
            if status in {ProviderPaymentStatus.PENDING, ProviderPaymentStatus.UNKNOWN}:
                continue
            await self._event_service.process_verified(
                VerifiedPaymentEvent(
                    provider=attempt.provider,
                    provider_event_id=f"reconcile_{uuid4().hex}",
                    provider_payment_id=attempt.provider_payment_id,
                    status=status,
                    amount=attempt.amount,
                    currency=attempt.currency,
                    occurred_at=now,
                )
            )

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Payment reconciliation iteration failed.")
            await asyncio.sleep(self._interval)
