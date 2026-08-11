from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from channels import ChatRequestRecord, ChatRequestStatus
from infrastructure.database import DatabasePool


class PostgresChatRequestRepository:
    """Durable idempotency boundary for synchronous REST chat requests."""

    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def begin(
        self,
        tenant_id: UUID,
        request_id: UUID,
        request_fingerprint: str,
        conversation_id: UUID,
        now: datetime,
    ) -> tuple[ChatRequestRecord, bool]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                """
                INSERT INTO rest_chat_requests (
                    tenant_id, request_id, request_fingerprint, conversation_id,
                    status, reply, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,'PENDING',NULL,$5,$5)
                ON CONFLICT (tenant_id, request_id) DO NOTHING
                RETURNING *
                """,
                tenant_id,
                request_id,
                request_fingerprint,
                conversation_id,
                now,
            )
            if row is not None:
                return self._record(row), True
            existing = await connection.fetchrow(
                """SELECT * FROM rest_chat_requests
                   WHERE tenant_id=$1 AND request_id=$2""",
                tenant_id,
                request_id,
            )
            if existing is None:
                raise RuntimeError("chat_request_missing_after_conflict")
            return self._record(existing), False

    async def mark_executing(
        self, tenant_id: UUID, request_id: UUID, now: datetime
    ) -> bool:
        result = await self._pool.pool.execute(
            """UPDATE rest_chat_requests SET status='EXECUTING', updated_at=$3
               WHERE tenant_id=$1 AND request_id=$2 AND status='PENDING'""",
            tenant_id,
            request_id,
            now,
        )
        return result == "UPDATE 1"

    async def complete(
        self,
        tenant_id: UUID,
        request_id: UUID,
        reply: str,
        now: datetime,
    ) -> None:
        result = await self._pool.pool.execute(
            """UPDATE rest_chat_requests
               SET status='COMPLETED', reply=$3, updated_at=$4
               WHERE tenant_id=$1 AND request_id=$2 AND status='EXECUTING'""",
            tenant_id,
            request_id,
            reply,
            now,
        )
        if result != "UPDATE 1":
            raise RuntimeError("chat_request_completion_conflict")

    async def mark_ambiguous(
        self, tenant_id: UUID, request_id: UUID, now: datetime
    ) -> None:
        await self._pool.pool.execute(
            """UPDATE rest_chat_requests SET status='AMBIGUOUS', updated_at=$3
               WHERE tenant_id=$1 AND request_id=$2 AND status='EXECUTING'""",
            tenant_id,
            request_id,
            now,
        )

    @asynccontextmanager
    async def conversation_lock(self, tenant_id: UUID, conversation_id: UUID):
        key = int.from_bytes(
            tenant_id.bytes[:4] + conversation_id.bytes[:4], "big", signed=True
        )
        async with self._pool.pool.acquire() as connection:
            acquired = await connection.fetchval("SELECT pg_try_advisory_lock($1)", key)
            try:
                yield bool(acquired)
            finally:
                if acquired:
                    await connection.execute("SELECT pg_advisory_unlock($1)", key)

    @staticmethod
    def _record(row) -> ChatRequestRecord:
        return ChatRequestRecord(
            tenant_id=row["tenant_id"],
            request_id=row["request_id"],
            request_fingerprint=row["request_fingerprint"],
            conversation_id=row["conversation_id"],
            status=ChatRequestStatus(row["status"]),
            reply=row["reply"],
        )
