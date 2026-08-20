import os
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest

from infrastructure.database.repositories import PostgresDeliveryZoneRepository

TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_DSN is None,
    reason="TEST_POSTGRES_DSN is required for PostGIS integration tests",
)


@pytest.mark.asyncio
async def test_postgis_covers_boundary_and_scopes_tenant_priority() -> None:
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=2)
    tenant, other = uuid4(), uuid4()
    first, second, foreign = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    polygon = "POLYGON((77 28,78 28,78 29,77 29,77 28))"
    try:
        async with pool.acquire() as connection:
            for zone_id, tenant_id, priority in (
                (first, tenant, 20),
                (second, tenant, 10),
                (foreign, other, 1),
            ):
                await connection.execute(
                    """INSERT INTO delivery_zones
                       (id,tenant_id,name,name_normalized,status,priority,boundary,
                        version,created_at,updated_at)
                       VALUES($1,$2,$3,$4,'ACTIVE',$5,
                         ST_Multi(ST_GeomFromText($6,4326)),1,$7,$7)""",
                    zone_id,
                    tenant_id,
                    str(zone_id),
                    str(zone_id),
                    priority,
                    polygon,
                    now,
                )
        repository = PostgresDeliveryZoneRepository(
            SimpleNamespace(pool=pool),
            max_vertices=500,
            max_rings=20,
            timeout_seconds=3,
            idempotency_hours=24,
        )
        inside = await repository.find_serviceable_zone(
            tenant, Decimal("28.5"), Decimal("77.5")
        )
        boundary = await repository.find_serviceable_zone(
            tenant, Decimal(28), Decimal(77)
        )
        outside = await repository.find_serviceable_zone(
            tenant, Decimal("27.9"), Decimal("77.5")
        )
        assert inside is not None and inside.id == second
        assert boundary is not None and boundary.id == second
        assert outside is None
    finally:
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM delivery_zones WHERE id=ANY($1::uuid[])",
                [first, second, foreign],
            )
        await pool.close()
