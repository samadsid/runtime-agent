from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from commerce.models.notification import NotificationEvent, NotificationStatus


class NotificationOutboxRepository(ABC):
    @abstractmethod
    async def claim_batch(
        self, *, now: datetime, batch_size: int, lease_seconds: int
    ) -> tuple[NotificationEvent, ...]: ...

    @abstractmethod
    async def suppress(
        self, notification_id: UUID, reason: str, processed_at: datetime
    ) -> None: ...

    @abstractmethod
    async def mark_failed(
        self,
        notification_id: UUID,
        *,
        status: NotificationStatus,
        error_code: str,
        next_attempt_at: datetime | None,
    ) -> None: ...
