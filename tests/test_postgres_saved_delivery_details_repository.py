from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest

from commerce.models import ChannelName
from commerce.repositories import StaleSavedDeliveryAddressError
from infrastructure.database.repositories import PostgresSavedDeliveryDetailsRepository

TEST_POSTGRES_DSN = os.getenv("TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(
    TEST_POSTGRES_DSN is None,
    reason="TEST_POSTGRES_DSN is required for PostgreSQL integration tests",
)


class PoolAdapter:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool


@pytest.mark.asyncio
async def test_saved_delivery_repository_is_tenant_scoped_versioned_and_serializes_defaults() -> (
    None
):
    assert TEST_POSTGRES_DSN is not None
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=4)
    first_tenant = uuid4()
    second_tenant = uuid4()
    customer_id = "integration-customer"
    repository = PostgresSavedDeliveryDetailsRepository(PoolAdapter(pool))  # type: ignore[arg-type]
    try:
        first_profile, home = await repository.save_details(
            first_tenant,
            ChannelName.DEVELOPMENT_HTTP,
            customer_id,
            "Sam",
            "9999",
            "Home",
            "1 Home Road",
            True,
            expect_profile_absent=True,
        )
        second_profile, _ = await repository.save_details(
            second_tenant,
            ChannelName.DEVELOPMENT_HTTP,
            customer_id,
            "Other",
            None,
            None,
            None,
            False,
            expect_profile_absent=True,
        )
        assert first_profile.id != second_profile.id
        assert await repository.list_addresses(second_tenant, first_profile.id) == ()
        assert home is not None

        office = await repository.add_address(
            first_tenant, first_profile.id, "Office", "2 Work Road", False
        )
        updated = await repository.update_address(
            first_tenant,
            first_profile.id,
            home.id,
            home.version,
            None,
            "New Home Road",
        )
        with pytest.raises(StaleSavedDeliveryAddressError):
            await repository.update_address(
                first_tenant,
                first_profile.id,
                home.id,
                home.version,
                None,
                "Stale Road",
            )

        await asyncio.gather(
            repository.set_default_address(first_tenant, first_profile.id, updated.id),
            repository.set_default_address(first_tenant, first_profile.id, office.id),
        )
        addresses = await repository.list_addresses(first_tenant, first_profile.id)
        assert sum(address.is_default for address in addresses) == 1
    finally:
        await pool.execute(
            "DELETE FROM saved_delivery_profiles WHERE tenant_id = ANY($1::uuid[])",
            [first_tenant, second_tenant],
        )
        await pool.close()
