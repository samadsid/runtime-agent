from __future__ import annotations

from collections.abc import Mapping
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

    async def send_template(
        self,
        recipient_id: str,
        content_sid: str,
        content_variables: Mapping[str, str],
        idempotency_key: UUID,
        status_callback_url: str,
    ) -> ProviderMessageResult: ...
