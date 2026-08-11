from __future__ import annotations

import hashlib

from commerce.models import VerifiedPaymentEvent
from commerce.payments import PaymentProvider
from commerce.repositories import PaymentRepository


class PaymentEventService:
    def __init__(
        self, repository: PaymentRepository, provider: PaymentProvider
    ) -> None:
        self._repository = repository
        self._provider = provider

    async def ingest(self, raw_body: bytes, signature: str):
        event = await self._provider.verify_and_parse_webhook(raw_body, signature)
        return await self._repository.process_event(
            event, hashlib.sha256(raw_body).hexdigest()
        )

    async def process_verified(self, event: VerifiedPaymentEvent):
        fingerprint = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
        return await self._repository.process_event(event, fingerprint)
