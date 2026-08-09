from __future__ import annotations

from types import TracebackType

import asyncpg
from typing_extensions import Self

from commerce.repositories import FulfilmentUnitOfWork
from infrastructure.database import DatabasePool

from .postgres_inventory_repository import PostgresInventoryRepository
from .postgres_order_repository import PostgresOrderRepository


class PostgresFulfilmentUnitOfWork(FulfilmentUnitOfWork):
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool
        self._connection: asyncpg.Connection | None = None
        self._transaction: asyncpg.Transaction | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._connection = await self._pool.pool.acquire()
        self._transaction = self._connection.transaction()
        await self._transaction.start()
        self.orders = PostgresOrderRepository(self._pool, self._connection)
        self.inventory = PostgresInventoryRepository(self._pool, self._connection)
        return self

    async def commit(self) -> None:
        if self._transaction is None:
            raise RuntimeError("Unit of work has not been entered.")
        await self._transaction.commit()
        self._committed = True

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self._transaction is not None and not self._committed:
                await self._transaction.rollback()
        finally:
            if self._connection is not None:
                await self._pool.pool.release(self._connection)
