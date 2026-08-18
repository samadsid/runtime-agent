from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg

from channels.models import (
    InboundMessage,
    MessageKind,
    NormalizedWebhookBatch,
    OutboundMessage,
    OutboundStatus,
    WhatsAppProviderName,
)
from commerce.models import ChannelName, NotificationEvent
from infrastructure.database import DatabasePool


class PostgresChannelRepository:
    """PostgreSQL authority for channel identity, inbox, outbox and callbacks."""

    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def ingest_meta_batch(
        self, *, tenant_id: UUID, batch: NormalizedWebhookBatch, received_at: datetime
    ) -> tuple[int, int]:
        """Atomically persist every valid normalized sibling in one Meta delivery."""
        inbound_created = 0
        status_created = 0
        async with self._pool.pool.acquire() as connection, connection.transaction():
            for message in sorted(
                batch.inbound, key=lambda item: item.provider_message_id
            ):
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                    f"meta_cloud:{message.provider_message_id}",
                )
                duplicate = await connection.fetchval(
                    """SELECT id FROM channel_inbound_messages
                       WHERE provider='meta_cloud' AND provider_message_id=$1""",
                    message.provider_message_id,
                )
                if duplicate is not None:
                    continue
                conversation = await connection.fetchrow(
                    """INSERT INTO channel_conversations (
                           id,tenant_id,channel,channel_customer_id,conversation_id,
                           last_inbound_at,created_at,updated_at
                       ) VALUES ($1,$2,$3,$4,$5,$6,$6,$6)
                       ON CONFLICT (tenant_id,channel,channel_customer_id)
                       DO UPDATE SET last_inbound_at=GREATEST(
                           channel_conversations.last_inbound_at,EXCLUDED.last_inbound_at
                       ),updated_at=EXCLUDED.updated_at
                       RETURNING conversation_id""",
                    uuid4(),
                    tenant_id,
                    ChannelName.WHATSAPP.value,
                    message.sender_id,
                    uuid4(),
                    received_at,
                )
                inserted = await connection.fetchval(
                    """INSERT INTO channel_inbound_messages (
                           id,tenant_id,channel,provider,provider_message_id,
                           conversation_id,sender_id,recipient_id,body,message_kind,
                           status,attempt_count,next_attempt_at,received_at
                       ) VALUES ($1,$2,$3,'meta_cloud',$4,$5,$6,$7,$8,$9,
                                 'RECEIVED',0,$10,$10)
                       ON CONFLICT (provider,provider_message_id) DO NOTHING
                       RETURNING id""",
                    uuid4(),
                    tenant_id,
                    ChannelName.WHATSAPP.value,
                    message.provider_message_id,
                    conversation["conversation_id"],
                    message.sender_id,
                    message.recipient_id,
                    message.body,
                    message.message_kind.value,
                    received_at,
                )
                inbound_created += int(inserted is not None)
            for event in batch.statuses:
                inserted = await connection.fetchval(
                    """INSERT INTO channel_delivery_events (
                           id,channel,provider,provider_message_id,status,error_code,
                           provider_event_at,received_at
                       ) VALUES ($1,$2,'meta_cloud',$3,$4,$5,$6,$7)
                       ON CONFLICT DO NOTHING RETURNING id""",
                    uuid4(),
                    ChannelName.WHATSAPP.value,
                    event.provider_message_id,
                    event.status.value,
                    event.error_code,
                    event.provider_event_at,
                    received_at,
                )
                if inserted is not None:
                    status_created += 1
                    await self._apply_delivery_status(
                        connection,
                        WhatsAppProviderName.META_CLOUD,
                        event.provider_message_id,
                        event.status,
                        event.error_code,
                        received_at,
                    )
        return inbound_created, status_created

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
        provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO,
    ) -> tuple[InboundMessage, bool]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
                f"{provider.value}:{provider_message_id}",
            )
            duplicate = await connection.fetchrow(
                """SELECT * FROM channel_inbound_messages
                   WHERE provider=$1 AND provider_message_id=$2""",
                provider.value,
                provider_message_id,
            )
            if duplicate is not None:
                return self._inbound(duplicate), False
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
                ChannelName.WHATSAPP.value,
                sender_id,
                conversation_id,
                received_at,
            )
            inbound_id = uuid4()
            inserted = await connection.fetchrow(
                """
                INSERT INTO channel_inbound_messages (
                    id, tenant_id, channel, provider, provider_message_id, conversation_id,
                    sender_id, recipient_id, body, message_kind, status,
                    attempt_count, next_attempt_at, received_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'RECEIVED',0,$11,$11)
                ON CONFLICT (provider, provider_message_id) DO NOTHING
                RETURNING *
                """,
                inbound_id,
                tenant_id,
                ChannelName.WHATSAPP.value,
                provider.value,
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
                   WHERE provider=$1 AND provider_message_id=$2""",
                provider.value,
                provider_message_id,
            )
            return self._inbound(duplicate), False

    async def claim_inbound_batch(
        self,
        batch_size: int,
        now: datetime,
        lease_seconds: int,
        provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO,
    ) -> list[InboundMessage]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT message.id
                    FROM channel_inbound_messages message
                    WHERE message.provider=$4 AND (
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
                provider.value,
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
                    id, tenant_id, channel, provider, conversation_id, source_inbound_id,
                    recipient_id, sender_id, body, status, attempt_count,
                    next_attempt_at, created_at, updated_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'PENDING',0,$10,$10,$10)
                ON CONFLICT (source_inbound_id) DO UPDATE
                    SET source_inbound_id=EXCLUDED.source_inbound_id
                RETURNING *
                """,
                uuid4(),
                inbound.tenant_id,
                inbound.channel,
                inbound.provider.value,
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
        self,
        batch_size: int,
        now: datetime,
        lease_seconds: int,
        provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO,
    ) -> list[OutboundMessage]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                """UPDATE channel_outbound_messages
                   SET status='AMBIGUOUS',last_error_code='expired_after_send_start',
                       lease_expires_at=NULL,updated_at=$1
                   WHERE provider=$2 AND status='SENDING'
                     AND lease_expires_at<=$1 AND send_started_at IS NOT NULL""",
                now,
                provider.value,
            )
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT id FROM channel_outbound_messages
                    WHERE provider=$4 AND (status IN ('PENDING','RETRYABLE')
                           OR (status='SENDING' AND lease_expires_at <= $1
                               AND send_started_at IS NULL))
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
                provider.value,
            )
            return [self._outbound(row) for row in rows]

    async def mark_send_started(self, outbound_id: UUID, now: datetime) -> None:
        updated = await self._pool.pool.execute(
            """UPDATE channel_outbound_messages SET send_started_at=$2,updated_at=$2
               WHERE id=$1 AND status='SENDING' AND send_started_at IS NULL""",
            outbound_id,
            now,
        )
        if not updated.endswith(" 1"):
            raise RuntimeError("outbound_not_sendable")

    async def accept_outbound(
        self, outbound_id: UUID, provider_message_id: str, now: datetime
    ) -> None:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            updated = await connection.fetchrow(
                """UPDATE channel_outbound_messages SET provider_message_id=$2,
                   status='ACCEPTED', sent_at=$3, updated_at=$3,
                   lease_expires_at=NULL, last_error_code=NULL
                   WHERE id=$1 AND status='SENDING' RETURNING provider""",
                outbound_id,
                provider_message_id,
                now,
            )
            if updated is not None:
                await self._apply_pending_events(
                    connection,
                    WhatsAppProviderName(updated["provider"]),
                    provider_message_id,
                    now,
                )

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
               lease_expires_at=NULL,send_started_at=NULL,updated_at=$5
               WHERE id=$1 AND status='SENDING'""",
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
        provider: WhatsAppProviderName = WhatsAppProviderName.TWILIO,
        provider_event_at: datetime | None = None,
    ) -> bool:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            inserted = await connection.execute(
                """INSERT INTO channel_delivery_events
                   (id,channel,provider,provider_message_id,status,error_code,provider_event_at,received_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   ON CONFLICT DO NOTHING""",
                uuid4(),
                ChannelName.WHATSAPP.value,
                provider.value,
                provider_message_id,
                status.value,
                error_code[:64] if error_code else None,
                provider_event_at,
                received_at,
            )
            if inserted.endswith(" 1"):
                await self._apply_delivery_status(
                    connection,
                    provider,
                    provider_message_id,
                    status,
                    error_code,
                    received_at,
                )
                return True
            return False

    async def conversation_last_inbound(self, conversation_id: UUID) -> datetime | None:
        return await self._pool.pool.fetchval(
            "SELECT last_inbound_at FROM channel_conversations WHERE conversation_id=$1",
            conversation_id,
        )

    async def latest_text_body(
        self, conversation_id: UUID, *, exclude_id: UUID
    ) -> str | None:
        return await self._pool.pool.fetchval(
            """SELECT body FROM channel_inbound_messages
               WHERE conversation_id=$1 AND id<>$2 AND message_kind='TEXT'
               ORDER BY received_at DESC,id DESC LIMIT 1""",
            conversation_id,
            exclude_id,
        )

    async def notification_for_outbound(
        self, outbound_id: UUID
    ) -> NotificationEvent | None:
        row = await self._pool.pool.fetchrow(
            """SELECT event.* FROM notification_outbox event
               JOIN notification_deliveries delivery ON delivery.notification_id=event.id
               JOIN channel_outbound_messages outbound
                 ON outbound.id=delivery.channel_outbound_message_id
                AND outbound.tenant_id=event.tenant_id
               WHERE outbound.id=$1""",
            outbound_id,
        )
        if row is None:
            return None
        data = dict(row)
        if isinstance(data["payload"], str):
            data["payload"] = json.loads(data["payload"])
        return NotificationEvent.model_validate(data)

    async def upgrade_notification_to_template(
        self,
        outbound_id: UUID,
        *,
        template_key: str,
        template_name: str,
        template_language: str | None,
        content_variables: dict[str, str],
        now: datetime,
    ) -> OutboundMessage:
        if not template_key or not template_name or not content_variables:
            raise ValueError("Invalid approved template content.")
        row = await self._pool.pool.fetchrow(
            """UPDATE channel_outbound_messages outbound
               SET content_mode='TEMPLATE',content_sid=$2,template_key=$3,
                   template_name=$2,template_language=$4,content_variables=$5::jsonb,
                   updated_at=$6
               WHERE outbound.id=$1 AND outbound.status='SENDING'
                 AND outbound.source_inbound_id IS NULL
                 AND EXISTS (
                     SELECT 1 FROM notification_deliveries delivery
                     WHERE delivery.channel_outbound_message_id=outbound.id
                 )
               RETURNING outbound.*""",
            outbound_id,
            template_name,
            template_key,
            template_language,
            json.dumps(content_variables),
            now,
        )
        if row is None:
            raise ValueError("Outbound notification cannot be upgraded.")
        return self._outbound(row)

    async def ping(self) -> bool:
        return (await self._pool.pool.fetchval("SELECT 1")) == 1

    async def has_unresolved_other_provider(
        self, provider: WhatsAppProviderName
    ) -> bool:
        return bool(
            await self._pool.pool.fetchval(
                """SELECT EXISTS(
                SELECT 1 FROM channel_inbound_messages
                WHERE provider<>$1 AND status IN ('RECEIVED','PROCESSING','RETRYABLE')
                UNION ALL
                SELECT 1 FROM channel_outbound_messages
                WHERE provider<>$1 AND status IN ('PENDING','SENDING','RETRYABLE','AMBIGUOUS')
            )""",
                provider.value,
            )
        )

    @staticmethod
    async def _apply_delivery_status(
        connection, provider, sid, status, error_code, now
    ) -> None:
        ranks = {"ACCEPTED": 1, "SENT": 2, "DELIVERED": 3, "READ": 4}
        row = await connection.fetchrow(
            "SELECT id,status FROM channel_outbound_messages WHERE provider=$1 AND provider_message_id=$2 FOR UPDATE",
            provider.value,
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

    async def _apply_pending_events(
        self, connection, provider: WhatsAppProviderName, sid: str, now: datetime
    ) -> None:
        rows = await connection.fetch(
            "SELECT status,error_code FROM channel_delivery_events WHERE provider=$1 AND provider_message_id=$2 ORDER BY received_at,id",
            provider.value,
            sid,
        )
        for row in rows:
            await self._apply_delivery_status(
                connection,
                provider,
                sid,
                OutboundStatus(row["status"]),
                row["error_code"],
                now,
            )

    @staticmethod
    def _inbound(row: asyncpg.Record) -> InboundMessage:
        return InboundMessage.model_validate(dict(row))

    @staticmethod
    def _outbound(row: asyncpg.Record) -> OutboundMessage:
        data = dict(row)
        if isinstance(data.get("content_variables"), str):
            data["content_variables"] = json.loads(data["content_variables"])
        return OutboundMessage.model_validate(data)
