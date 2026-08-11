from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg

from channels.models import (
    InboundMessage,
    MessageKind,
    OutboundMessage,
    OutboundStatus,
)
from commerce.models import ChannelName
from infrastructure.database import DatabasePool


class PostgresChannelRepository:
    """PostgreSQL authority for channel identity, inbox, outbox and callbacks."""

    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def ingest_inbound(
        self,
        *,
        tenant_id: UUID,
        provider_message_id: str,
        sender_id: str,
        recipient_id: str,
        body: str,
        message_kind: MessageKind,
        received_at: datetime,
    ) -> tuple[InboundMessage, bool]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            conversation_id = uuid4()
            row = await connection.fetchrow(
                """
                INSERT INTO channel_conversations (
                    id, tenant_id, channel, channel_customer_id, conversation_id,
                    last_inbound_at, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$6,$6)
                ON CONFLICT (tenant_id, channel, channel_customer_id)
                DO UPDATE SET last_inbound_at = GREATEST(
                    channel_conversations.last_inbound_at, EXCLUDED.last_inbound_at
                ), updated_at = EXCLUDED.updated_at
                RETURNING conversation_id
                """,
                uuid4(),
                tenant_id,
                ChannelName.TWILIO_WHATSAPP.value,
                sender_id,
                conversation_id,
                received_at,
            )
            inbound_id = uuid4()
            inserted = await connection.fetchrow(
                """
                INSERT INTO channel_inbound_messages (
                    id, tenant_id, channel, provider_message_id, conversation_id,
                    sender_id, recipient_id, body, message_kind, status,
                    attempt_count, next_attempt_at, received_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'RECEIVED',0,$10,$10)
                ON CONFLICT (channel, provider_message_id) DO NOTHING
                RETURNING *
                """,
                inbound_id,
                tenant_id,
                ChannelName.TWILIO_WHATSAPP.value,
                provider_message_id,
                row["conversation_id"],
                sender_id,
                recipient_id,
                body,
                message_kind.value,
                received_at,
            )
            if inserted is not None:
                return self._inbound(inserted), True
            duplicate = await connection.fetchrow(
                """SELECT * FROM channel_inbound_messages
                   WHERE channel=$1 AND provider_message_id=$2""",
                ChannelName.TWILIO_WHATSAPP.value,
                provider_message_id,
            )
            return self._inbound(duplicate), False

    async def claim_inbound_batch(
        self, batch_size: int, now: datetime, lease_seconds: int
    ) -> list[InboundMessage]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT message.id
                    FROM channel_inbound_messages message
                    WHERE (
                        message.status IN ('RECEIVED','RETRYABLE')
                        OR (message.status='PROCESSING' AND message.lease_expires_at <= $1)
                    ) AND message.next_attempt_at <= $1
                    AND NOT EXISTS (
                        SELECT 1 FROM channel_inbound_messages earlier
                        WHERE earlier.tenant_id=message.tenant_id
                          AND earlier.conversation_id=message.conversation_id
                          AND (earlier.received_at, earlier.id) < (message.received_at, message.id)
                          AND earlier.status NOT IN ('PROCESSED','DEAD_LETTER')
                    )
                    ORDER BY message.received_at, message.id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $2
                )
                UPDATE channel_inbound_messages message
                SET status='PROCESSING', attempt_count=attempt_count+1,
                    lease_expires_at=$1 + ($3 * interval '1 second')
                FROM candidates WHERE message.id=candidates.id
                RETURNING message.*
                """,
                now,
                batch_size,
                lease_seconds,
            )
            return [self._inbound(row) for row in rows]

    @asynccontextmanager
    async def conversation_lock(self, tenant_id: UUID, conversation_id: UUID):
        """Serialize one LangGraph thread without holding a database transaction."""
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

    async def complete_inbound(
        self, inbound: InboundMessage, reply: str, sender_id: str, now: datetime
    ) -> OutboundMessage:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                """
                INSERT INTO channel_outbound_messages (
                    id, tenant_id, channel, conversation_id, source_inbound_id,
                    recipient_id, sender_id, body, status, attempt_count,
                    next_attempt_at, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'PENDING',0,$9,$9,$9)
                ON CONFLICT (source_inbound_id) DO UPDATE
                    SET source_inbound_id=EXCLUDED.source_inbound_id
                RETURNING *
                """,
                uuid4(),
                inbound.tenant_id,
                inbound.channel,
                inbound.conversation_id,
                inbound.id,
                inbound.sender_id,
                sender_id,
                reply,
                now,
            )
            await connection.execute(
                """UPDATE channel_inbound_messages
                   SET status='PROCESSED', processed_at=$2, lease_expires_at=NULL,
                       last_error_code=NULL WHERE id=$1""",
                inbound.id,
                now,
            )
            return self._outbound(row)

    async def fail_inbound(
        self,
        inbound_id: UUID,
        *,
        retry: bool,
        error_code: str,
        next_attempt_at: datetime,
    ) -> None:
        await self._pool.pool.execute(
            """UPDATE channel_inbound_messages
               SET status=$2, next_attempt_at=$3, lease_expires_at=NULL,
                   last_error_code=$4 WHERE id=$1 AND status='PROCESSING'""",
            inbound_id,
            "RETRYABLE" if retry else "DEAD_LETTER",
            next_attempt_at,
            error_code[:64],
        )

    async def claim_outbound_batch(
        self, batch_size: int, now: datetime, lease_seconds: int
    ) -> list[OutboundMessage]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT id FROM channel_outbound_messages
                    WHERE (status IN ('PENDING','RETRYABLE')
                           OR (status='SENDING' AND lease_expires_at <= $1))
                      AND next_attempt_at <= $1
                    ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT $2
                )
                UPDATE channel_outbound_messages message
                SET status='SENDING', attempt_count=attempt_count+1,
                    lease_expires_at=$1 + ($3 * interval '1 second'), updated_at=$1
                FROM candidates WHERE message.id=candidates.id RETURNING message.*
                """,
                now,
                batch_size,
                lease_seconds,
            )
            return [self._outbound(row) for row in rows]

    async def accept_outbound(
        self, outbound_id: UUID, provider_message_id: str, now: datetime
    ) -> None:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """UPDATE channel_outbound_messages SET provider_message_id=$2,
                   status='ACCEPTED', sent_at=$3, updated_at=$3,
                   lease_expires_at=NULL, last_error_code=NULL
                   WHERE id=$1 AND status='SENDING'""",
                outbound_id,
                provider_message_id,
                now,
            )
            await self._apply_pending_events(connection, provider_message_id, now)

    async def fail_outbound(
        self,
        outbound_id: UUID,
        status: OutboundStatus,
        error_code: str,
        now: datetime,
        next_attempt_at: datetime | None = None,
    ) -> None:
        await self._pool.pool.execute(
            """UPDATE channel_outbound_messages SET status=$2,
               last_error_code=$3, next_attempt_at=COALESCE($4,next_attempt_at),
               lease_expires_at=NULL, updated_at=$5 WHERE id=$1 AND status='SENDING'""",
            outbound_id,
            status.value,
            error_code[:64],
            next_attempt_at,
            now,
        )

    async def record_delivery_event(
        self,
        provider_message_id: str,
        status: OutboundStatus,
        error_code: str | None,
        received_at: datetime,
    ) -> bool:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            inserted = await connection.execute(
                """INSERT INTO channel_delivery_events
                   (id,channel,provider_message_id,status,error_code,received_at)
                   VALUES ($1,$2,$3,$4,$5,$6)
                   ON CONFLICT (channel,provider_message_id,status) DO NOTHING""",
                uuid4(),
                ChannelName.TWILIO_WHATSAPP.value,
                provider_message_id,
                status.value,
                error_code[:64] if error_code else None,
                received_at,
            )
            if inserted.endswith(" 1"):
                await self._apply_delivery_status(
                    connection, provider_message_id, status, error_code, received_at
                )
                return True
            return False

    async def conversation_last_inbound(self, conversation_id: UUID) -> datetime | None:
        return await self._pool.pool.fetchval(
            "SELECT last_inbound_at FROM channel_conversations WHERE conversation_id=$1",
            conversation_id,
        )

    async def ping(self) -> bool:
        return (await self._pool.pool.fetchval("SELECT 1")) == 1

    @staticmethod
    async def _apply_delivery_status(connection, sid, status, error_code, now) -> None:
        ranks = {"ACCEPTED": 1, "SENT": 2, "DELIVERED": 3, "READ": 4}
        row = await connection.fetchrow(
            "SELECT id,status FROM channel_outbound_messages WHERE channel=$1 AND provider_message_id=$2 FOR UPDATE",
            ChannelName.TWILIO_WHATSAPP.value,
            sid,
        )
        if row is None or row["status"] in {
            "FAILED",
            "READ",
            "DEAD_LETTER",
            "TEMPLATE_REQUIRED",
            "AMBIGUOUS",
        }:
            return
        if status == OutboundStatus.FAILED or ranks.get(status.value, 0) > ranks.get(
            row["status"], 0
        ):
            await connection.execute(
                "UPDATE channel_outbound_messages SET status=$2,last_error_code=$3,updated_at=$4 WHERE id=$1",
                row["id"],
                status.value,
                error_code[:64] if error_code else None,
                now,
            )

    async def _apply_pending_events(self, connection, sid: str, now: datetime) -> None:
        rows = await connection.fetch(
            "SELECT status,error_code FROM channel_delivery_events WHERE channel=$1 AND provider_message_id=$2 ORDER BY received_at,id",
            ChannelName.TWILIO_WHATSAPP.value,
            sid,
        )
        for row in rows:
            await self._apply_delivery_status(
                connection, sid, OutboundStatus(row["status"]), row["error_code"], now
            )

    @staticmethod
    def _inbound(row: asyncpg.Record) -> InboundMessage:
        return InboundMessage.model_validate(dict(row))

    @staticmethod
    def _outbound(row: asyncpg.Record) -> OutboundMessage:
        return OutboundMessage.model_validate(dict(row))
