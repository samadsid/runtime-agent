from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.jobs.channel_workers import PeriodicChannelWorker
from infrastructure.database.repositories import PostgresNotificationOutboxRepository

logger = logging.getLogger(__name__)


class NotificationReconciliationJob(PeriodicChannelWorker):
    def __init__(
        self,
        repository: PostgresNotificationOutboxRepository,
        batch_size: int,
        interval_seconds: float,
    ) -> None:
        super().__init__(interval_seconds, "notification_reconciliation")
        self._repository = repository
        self._batch_size = batch_size

    async def run_once(self) -> None:
        result = await self._repository.reconcile(
            now=datetime.now(timezone.utc), batch_size=self._batch_size
        )
        if any(result.values()):
            logger.warning(
                "Notification reconciliation found inconsistencies.",
                extra={"event": "notification_reconciliation", **result},
            )
