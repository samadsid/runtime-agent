from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .models import ProviderMessageResult


class OutboundMessageProvider(Protocol):
    async def send_text(
        self,
        recipient_id: str,
        body: str,
        idempotency_key: UUID,
        status_callback_url: str,
    ) -> ProviderMessageResult: ...
