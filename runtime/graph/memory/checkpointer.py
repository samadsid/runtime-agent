from __future__ import annotations

from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from commerce.models import (
    Cart,
    CartItem,
    CheckoutState,
    CommerceSession,
    Order,
    OrderItem,
    OrderStatusHistory,
    OrderSummary,
    PendingCartClear,
    PendingOrderCancellation,
    Product,
)


class GraphCheckpointer:
    """Owns the configured LangGraph checkpointer and its async lifecycle."""

    def __init__(
        self,
        backend: Literal["memory", "postgres"] = "memory",
        postgres_dsn: str | None = None,
    ) -> None:
        self._backend = backend
        self._postgres_dsn = postgres_dsn
        self._serializer = JsonPlusSerializer(
            allowed_msgpack_modules=(
                CommerceSession,
                CheckoutState,
                Cart,
                CartItem,
                Order,
                OrderItem,
                OrderStatusHistory,
                OrderSummary,
                PendingCartClear,
                PendingOrderCancellation,
                Product,
            )
        )
        self._pool = None
        self._checkpointer: BaseCheckpointSaver | None = (
            MemorySaver(serde=self._serializer) if backend == "memory" else None
        )

    async def start(self) -> None:
        if self._backend == "memory" or self._checkpointer is not None:
            return
        if self._postgres_dsn is None:
            raise ValueError("A PostgreSQL DSN is required for checkpoint persistence.")

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        self._pool = AsyncConnectionPool(
            conninfo=self._postgres_dsn,
            min_size=1,
            max_size=10,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
            open=False,
        )
        await self._pool.open()
        self._checkpointer = AsyncPostgresSaver(self._pool, serde=self._serializer)
        await self._checkpointer.setup()

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
        if self._backend == "postgres":
            self._checkpointer = None

    @property
    def instance(self) -> BaseCheckpointSaver:
        if self._checkpointer is None:
            raise RuntimeError("Graph checkpointer has not been started.")
        return self._checkpointer
