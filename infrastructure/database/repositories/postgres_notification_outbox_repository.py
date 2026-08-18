from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from channels.models import (
    ApprovedTemplateMessage,
    ChannelConversation,
    WhatsAppProviderName,
)
from commerce.models import (
    ChannelName,
    NotificationContentMode,
    NotificationEvent,
    NotificationStatus,
    NotificationTemplate,
    NotificationType,
    OrderNotificationPayload,
)
from commerce.repositories import NotificationOutboxRepository
from infrastructure.database import DatabasePool

_ORDER_TYPES = {
    "CONFIRMED": NotificationType.ORDER_CONFIRMED,
    "PREPARING": NotificationType.ORDER_PREPARING,
    "OUT_FOR_DELIVERY": NotificationType.ORDER_OUT_FOR_DELIVERY,
    "DELIVERED": NotificationType.ORDER_DELIVERED,
    "CANCELLED": NotificationType.ORDER_CANCELLED,
}


class PostgresNotificationOutboxRepository(NotificationOutboxRepository):
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    @staticmethod
    async def append_order_transition(
        connection: asyncpg.Connection, order_id: UUID, history_id: UUID
    ) -> UUID | None:
        row = await connection.fetchrow(
            """
            SELECT history.to_status, history.created_at, order_row.payment_method,
                   order_row.conversation_id, cart.tenant_id,
                   SUM(item.unit_price * item.quantity) AS total_amount,
                   MIN(item.currency) AS currency,
                   COUNT(DISTINCT item.currency) AS currency_count
            FROM order_status_history history
            JOIN orders order_row ON order_row.id=history.order_id
            JOIN carts cart ON cart.id=order_row.source_cart_id
            JOIN order_items item ON item.order_id=order_row.id
            WHERE history.id=$1 AND order_row.id=$2
            GROUP BY history.to_status, history.created_at, order_row.payment_method,
                     order_row.conversation_id, cart.tenant_id
            """,
            history_id,
            order_id,
        )
        if row is None or row["to_status"] not in _ORDER_TYPES:
            return None
        if row["currency_count"] != 1:
            raise ValueError(
                "An order notification requires one authoritative currency."
            )
        channel = await connection.fetchrow(
            """
            SELECT id, channel FROM channel_conversations
            WHERE tenant_id=$1 AND conversation_id=$2
            """,
            row["tenant_id"],
            row["conversation_id"],
        )
        payload = OrderNotificationPayload(
            order_reference=str(order_id),
            order_status=row["to_status"],
            payment_method=row["payment_method"],
            currency=row["currency"],
            total_amount=format(Decimal(row["total_amount"]), "f"),
            occurred_at=row["created_at"],
        )
        notification_id = uuid4()
        inserted = await connection.fetchval(
            """
            INSERT INTO notification_outbox (
                id,tenant_id,notification_type,source_type,source_id,order_id,
                customer_channel_id,preferred_channel,locale,payload,payload_version,
                status,attempt_count,available_at,created_at
            ) VALUES ($1,$2,$3,'ORDER_STATUS_HISTORY',$4,$5,$6,$7,NULL,$8::jsonb,1,
                      'PENDING',0,$9,$9)
            ON CONFLICT (tenant_id,source_type,source_id,notification_type) DO NOTHING
            RETURNING id
            """,
            notification_id,
            row["tenant_id"],
            _ORDER_TYPES[row["to_status"]].value,
            history_id,
            order_id,
            channel["id"] if channel else None,
            channel["channel"] if channel else ChannelName.DEVELOPMENT_HTTP.value,
            json.dumps(payload.model_dump(mode="json")),
            row["created_at"],
        )
        return inserted

    async def claim_batch(
        self, *, now: datetime, batch_size: int, lease_seconds: int
    ) -> tuple[NotificationEvent, ...]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            rows = await connection.fetch(
                """
                WITH candidates AS (
                    SELECT id FROM notification_outbox
                    WHERE (
                        status IN ('PENDING','RETRYABLE')
                        OR (status='PROCESSING' AND lease_expires_at <= $1)
                    ) AND available_at <= $1
                    ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT $2
                )
                UPDATE notification_outbox event
                SET status='PROCESSING',attempt_count=attempt_count+1,
                    lease_expires_at=$1 + ($3 * interval '1 second')
                FROM candidates WHERE event.id=candidates.id
                RETURNING event.*
                """,
                now,
                batch_size,
                lease_seconds,
            )
            return tuple(self._event(row) for row in rows)

    async def resolve_channel(
        self, event: NotificationEvent
    ) -> ChannelConversation | None:
        if event.customer_channel_id is None:
            return None
        row = await self._pool.pool.fetchrow(
            """SELECT * FROM channel_conversations
               WHERE id=$1 AND tenant_id=$2 AND channel=$3""",
            event.customer_channel_id,
            event.tenant_id,
            ChannelName.WHATSAPP.value,
        )
        return ChannelConversation.model_validate(dict(row)) if row else None

    async def dispatch_to_channel(
        self,
        event: NotificationEvent,
        target: ChannelConversation,
        template: NotificationTemplate,
        *,
        body: str,
        sender_id: str,
        content_mode: NotificationContentMode,
        content_variables: dict[str, str] | None,
        provider: WhatsAppProviderName,
        provider_template: ApprovedTemplateMessage | None,
        now: datetime,
    ) -> UUID:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            existing = await connection.fetchval(
                """SELECT channel_outbound_message_id FROM notification_deliveries
                   WHERE notification_id=$1 AND channel=$2""",
                event.id,
                target.channel.value,
            )
            if existing is None:
                outbound_id = uuid4()
                await connection.execute(
                    """
                    INSERT INTO channel_outbound_messages (
                        id,tenant_id,channel,provider,conversation_id,source_inbound_id,
                        recipient_id,sender_id,body,content_mode,content_sid,
                        content_variables,template_key,template_name,template_language,
                        status,attempt_count,next_attempt_at,
                        created_at,updated_at
                    ) VALUES ($1,$2,$3,$4,$5,NULL,$6,$7,$8,$9,$10,$11::jsonb,
                              $12,$13,$14,'PENDING',0,$15,$15,$15)
                    """,
                    outbound_id,
                    event.tenant_id,
                    target.channel.value,
                    provider.value,
                    target.conversation_id,
                    target.channel_customer_id,
                    sender_id,
                    body,
                    content_mode.value,
                    provider_template.name if provider_template else None,
                    (
                        json.dumps(content_variables)
                        if content_mode == NotificationContentMode.TEMPLATE
                        and content_variables is not None
                        else None
                    ),
                    template.key if provider_template else None,
                    provider_template.name if provider_template else None,
                    provider_template.language if provider_template else None,
                    now,
                )
                await connection.execute(
                    """INSERT INTO notification_deliveries
                       (id,notification_id,channel,channel_outbound_message_id,
                        template_key,template_version,created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                    uuid4(),
                    event.id,
                    target.channel.value,
                    outbound_id,
                    template.key,
                    template.version,
                    now,
                )
            else:
                outbound_id = existing
            await connection.execute(
                """UPDATE notification_outbox
                   SET status='DISPATCHED',processed_at=$2,lease_expires_at=NULL,
                       last_error_code=NULL WHERE id=$1 AND status='PROCESSING'""",
                event.id,
                now,
            )
            return outbound_id

    async def suppress(
        self, notification_id: UUID, reason: str, processed_at: datetime
    ) -> None:
        await self._pool.pool.execute(
            """UPDATE notification_outbox SET status='SUPPRESSED',processed_at=$2,
               lease_expires_at=NULL,last_error_code=$3
               WHERE id=$1 AND status='PROCESSING'""",
            notification_id,
            processed_at,
            reason[:64],
        )

    async def mark_failed(
        self,
        notification_id: UUID,
        *,
        status: NotificationStatus,
        error_code: str,
        next_attempt_at: datetime | None,
    ) -> None:
        if status not in {NotificationStatus.RETRYABLE, NotificationStatus.DEAD_LETTER}:
            raise ValueError("Invalid notification failure status.")
        await self._pool.pool.execute(
            """UPDATE notification_outbox SET status=$2,
               available_at=COALESCE($3,available_at),lease_expires_at=NULL,
               last_error_code=$4,processed_at=CASE WHEN $2='DEAD_LETTER' THEN now() ELSE NULL END
               WHERE id=$1 AND status='PROCESSING'""",
            notification_id,
            status.value,
            next_attempt_at,
            error_code[:64],
        )

    async def reconcile(self, *, now: datetime, batch_size: int) -> dict[str, int]:
        """Repair safe outbox inconsistencies and report operator-only failures."""
        async with self._pool.pool.acquire() as connection, connection.transaction():
            missing = await connection.fetch(
                """
                SELECT history.id,history.order_id
                FROM order_status_history history
                JOIN orders order_row ON order_row.id=history.order_id
                JOIN carts cart ON cart.id=order_row.source_cart_id
                WHERE history.to_status IN (
                    'CONFIRMED','PREPARING','OUT_FOR_DELIVERY','DELIVERED','CANCELLED'
                ) AND NOT EXISTS (
                    SELECT 1 FROM notification_outbox event
                    WHERE event.tenant_id=cart.tenant_id
                      AND event.source_type='ORDER_STATUS_HISTORY'
                      AND event.source_id=history.id
                      AND event.notification_type=CASE history.to_status
                          WHEN 'CONFIRMED' THEN 'ORDER_CONFIRMED'
                          WHEN 'PREPARING' THEN 'ORDER_PREPARING'
                          WHEN 'OUT_FOR_DELIVERY' THEN 'ORDER_OUT_FOR_DELIVERY'
                          WHEN 'DELIVERED' THEN 'ORDER_DELIVERED'
                          WHEN 'CANCELLED' THEN 'ORDER_CANCELLED'
                      END
                )
                ORDER BY history.created_at,history.id
                FOR UPDATE OF history SKIP LOCKED LIMIT $1
                """,
                batch_size,
            )
            repaired = 0
            for row in missing:
                if await self.append_order_transition(
                    connection, row["order_id"], row["id"]
                ) is not None:
                    repaired += 1
            dispatched_without_delivery = await connection.fetchval(
                """SELECT COUNT(*) FROM notification_outbox event
                   WHERE event.status='DISPATCHED' AND NOT EXISTS (
                       SELECT 1 FROM notification_deliveries delivery
                       WHERE delivery.notification_id=event.id
                   )"""
            )
            if dispatched_without_delivery:
                await connection.execute(
                    """UPDATE notification_outbox event
                       SET status='RETRYABLE',available_at=$1,processed_at=NULL,
                           last_error_code='reconciled_missing_delivery'
                       WHERE event.status='DISPATCHED' AND NOT EXISTS (
                           SELECT 1 FROM notification_deliveries delivery
                           WHERE delivery.notification_id=event.id
                       )""",
                    now,
                )
            terminal_failures = await connection.fetchval(
                """SELECT COUNT(*) FROM notification_deliveries delivery
                   JOIN channel_outbound_messages outbound
                     ON outbound.id=delivery.channel_outbound_message_id
                   WHERE outbound.status IN ('FAILED','DEAD_LETTER','AMBIGUOUS')"""
            )
            return {
                "missing_repaired": repaired,
                "dispatched_repaired": int(dispatched_without_delivery),
                "terminal_failures": int(terminal_failures),
            }

    @staticmethod
    def _event(row: asyncpg.Record) -> NotificationEvent:
        data = dict(row)
        if isinstance(data["payload"], str):
            data["payload"] = json.loads(data["payload"])
        return NotificationEvent.model_validate(data)
