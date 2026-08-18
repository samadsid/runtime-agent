from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .models import ApprovedTemplateMessage, ProviderMessageResult


class RetryableSendError(RuntimeError):
    pass


class PermanentSendError(RuntimeError):
    pass


class AmbiguousSendError(RuntimeError):
    pass


class OutboundMessageProvider(Protocol):
    async def send_text(
        self,
        recipient_id: str,
        body: str,
        idempotency_key: UUID,
    ) -> ProviderMessageResult: ...

    async def send_template(
        self,
        recipient_id: str,
        template: ApprovedTemplateMessage,
        idempotency_key: UUID,
    ) -> ProviderMessageResult: ...
