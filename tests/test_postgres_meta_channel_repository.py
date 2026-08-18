from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import asyncpg
import pytest

from channels.models import (
    MessageKind,
    NormalizedDeliveryStatusEvent,
    NormalizedInboundEvent,
    NormalizedWebhookBatch,
    OutboundStatus,
)
from infrastructure.database.repositories import PostgresChannelRepository

TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_DSN is None,
    reason="TEST_POSTGRES_DSN is required for PostgreSQL integration tests",
)


class PoolAdapter:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool


@pytest.mark.asyncio
async def test_meta_batch_is_atomic_deduplicated_and_does_not_refresh_on_replay() -> (
    None
):
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=2)
    repository = PostgresChannelRepository(PoolAdapter(pool))  # type: ignore[arg-type]
    tenant_id = uuid4()
    suffix = uuid4().hex
    received_at = datetime.now(timezone.utc)
    wamid = f"wamid.{suffix}"
    status_wamid = f"wamid.{uuid4().hex}"
    batch = NormalizedWebhookBatch(
        inbound=(
            NormalizedInboundEvent(
                provider_message_id=wamid,
                sender_id="+919876543210",
                recipient_id="123456",
                body="hello",
                message_kind=MessageKind.TEXT,
            ),
        ),
        statuses=(
            NormalizedDeliveryStatusEvent(
                provider_message_id=status_wamid,
                status=OutboundStatus.DELIVERED,
                provider_event_at=received_at,
                error_code=None,
            ),
        ),
    )
    try:
        assert await repository.ingest_meta_batch(
            tenant_id=tenant_id, batch=batch, received_at=received_at
        ) == (1, 1)
        assert await repository.ingest_meta_batch(
            tenant_id=tenant_id,
            batch=batch,
            received_at=received_at + timedelta(hours=1),
        ) == (0, 0)
        last_inbound = await pool.fetchval(
            "SELECT last_inbound_at FROM channel_conversations WHERE tenant_id=$1",
            tenant_id,
        )
        assert last_inbound == received_at
        assert (
            await pool.fetchval(
                """SELECT count(*) FROM channel_inbound_messages
                   WHERE provider='meta_cloud' AND provider_message_id=$1""",
                wamid,
            )
            == 1
        )
        assert (
            await pool.fetchval(
                """SELECT count(*) FROM channel_delivery_events
                   WHERE provider='meta_cloud' AND provider_message_id=$1""",
                status_wamid,
            )
            == 1
        )
    finally:
        await pool.execute(
            "DELETE FROM channel_delivery_events WHERE provider_message_id=$1",
            status_wamid,
        )
        await pool.execute(
            "DELETE FROM channel_inbound_messages WHERE provider_message_id=$1", wamid
        )
        await pool.execute(
            "DELETE FROM channel_conversations WHERE tenant_id=$1", tenant_id
        )
        await pool.close()
