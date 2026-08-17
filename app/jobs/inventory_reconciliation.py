from __future__ import annotations

import asyncio
import logging

from app.observability.staff_metrics import INVENTORY_RECONCILIATION_FAILURES
from infrastructure.database.repositories.postgres_catalog_admin_repository import (
    PostgresCatalogAdminRepository,
)

logger = logging.getLogger(__name__)


class InventoryReconciliationJob:
    def __init__(self, repository: PostgresCatalogAdminRepository, batch_size: int, interval_seconds: int) -> None:
        self._repository = repository
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
        for category, tenant_id, product_id in await self._repository.reconciliation_failures(self._batch_size):
            INVENTORY_RECONCILIATION_FAILURES.labels(category).inc()
            logger.critical("Inventory reconciliation mismatch.", extra={"event": "inventory_reconciliation_failure", "category": category, "tenant_id": str(tenant_id), "product_id": str(product_id)})

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("Inventory reconciliation iteration failed.")
            await asyncio.sleep(self._interval)
