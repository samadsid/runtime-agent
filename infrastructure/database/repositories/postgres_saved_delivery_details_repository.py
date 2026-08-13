from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from uuid import UUID, uuid4

import asyncpg

from commerce.models import ChannelName, SavedDeliveryAddress, SavedDeliveryProfile
from commerce.repositories import (
    SavedDeliveryAddressNotFoundError,
    SavedDeliveryDetailsRepository,
    SavedDeliveryPersistenceError,
    SavedDeliveryProfileConflictError,
    StaleSavedDeliveryAddressError,
)
from infrastructure.database import DatabasePool

logger = logging.getLogger(__name__)


class PostgresSavedDeliveryDetailsRepository(SavedDeliveryDetailsRepository):
    def __init__(
        self,
        pool: DatabasePool,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        self._pool = pool
        self._connection = connection

    async def get_profile(
        self, tenant_id: UUID, channel: ChannelName, channel_customer_id: str
    ) -> SavedDeliveryProfile | None:
        if self._connection is None:
            try:
                async with self._pool.pool.acquire() as connection:
                    return await self._with(connection).get_profile(
                        tenant_id, channel, channel_customer_id
                    )
            except asyncpg.PostgresError as error:
                raise SavedDeliveryPersistenceError(
                    "Saved delivery profile is temporarily unavailable."
                ) from error
        row = await self._connection.fetchrow(
            """
            SELECT id, tenant_id, channel, channel_customer_id, customer_name,
                   phone_number, phone_verified, onboarding_status,
                   profile_consent_version, profile_consented_at,
                   onboarding_request_id, created_at, updated_at
            FROM saved_delivery_profiles
            WHERE tenant_id = $1 AND channel = $2 AND channel_customer_id = $3
            """,
            tenant_id,
            channel.value,
            channel_customer_id,
        )
        return self._profile(row) if row is not None else None

    async def complete_onboarding(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str,
        customer_name: str,
        phone_number: str,
        delivery_address: str,
        consent_version: str,
        consented_at: datetime,
        request_id: str,
        address_label: str,
    ) -> SavedDeliveryProfile:
        if self._connection is None:
            for attempt in range(3):
                try:
                    async with (
                        self._pool.pool.acquire() as connection,
                        connection.transaction(),
                    ):
                        return await self._with(connection).complete_onboarding(
                            tenant_id,
                            channel,
                            channel_customer_id,
                            customer_name,
                            phone_number,
                            delivery_address,
                            consent_version,
                            consented_at,
                            request_id,
                            address_label,
                        )
                except SavedDeliveryProfileConflictError:
                    raise
                except asyncpg.PostgresError as error:
                    if error.sqlstate not in {"40P01", "40001"} or attempt == 2:
                        raise SavedDeliveryPersistenceError(
                            "Customer onboarding is temporarily unavailable."
                        ) from error
                    logger.warning(
                        "Retrying customer onboarding transaction.",
                        extra={
                            "event": "customer_onboarding_concurrency_retry",
                            "attempt": attempt + 1,
                            "sqlstate": error.sqlstate,
                        },
                    )
                    await asyncio.sleep(0.025 * (2**attempt))
            raise AssertionError("Onboarding retry loop did not return or raise.")

        connection = self._connection
        await connection.execute(
            """
            INSERT INTO saved_delivery_profiles (
                id, tenant_id, channel, channel_customer_id, customer_name,
                phone_number, phone_verified, onboarding_status, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, NULL, NULL, FALSE, 'INCOMPLETE', now(), now())
            ON CONFLICT (tenant_id, channel, channel_customer_id) DO NOTHING
            """,
            uuid4(),
            tenant_id,
            channel.value,
            channel_customer_id,
        )
        current = await connection.fetchrow(
            """
            SELECT id, customer_name, phone_number, onboarding_status,
                   onboarding_request_id
            FROM saved_delivery_profiles
            WHERE tenant_id=$1 AND channel=$2 AND channel_customer_id=$3
            FOR UPDATE
            """,
            tenant_id,
            channel.value,
            channel_customer_id,
        )
        if current is None:
            raise SavedDeliveryPersistenceError(
                "Saved delivery profile was unavailable."
            )
        if current["onboarding_status"] == "COMPLETED":
            matching_address = await connection.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1 FROM saved_delivery_addresses
                    WHERE profile_id=$1 AND delivery_address=$2
                )
                """,
                current["id"],
                delivery_address,
            )
            if current["onboarding_request_id"] == request_id or (
                current["customer_name"] == customer_name
                and current["phone_number"] == phone_number
                and matching_address
            ):
                profile = await self.get_profile(
                    tenant_id, channel, channel_customer_id
                )
                assert profile is not None
                return profile
            raise SavedDeliveryProfileConflictError(
                "Customer onboarding was already completed."
            )
        for existing, proposed in (
            (current["customer_name"], customer_name),
            (current["phone_number"], phone_number),
        ):
            if existing is not None and existing != proposed:
                raise SavedDeliveryProfileConflictError(
                    "Onboarding cannot overwrite saved profile values."
                )
        addresses = await connection.fetch(
            """
            SELECT id, delivery_address, is_default
            FROM saved_delivery_addresses
            WHERE profile_id=$1 ORDER BY is_default DESC, created_at, id
            FOR UPDATE
            """,
            current["id"],
        )
        if addresses:
            if not any(
                row["delivery_address"] == delivery_address for row in addresses
            ):
                raise SavedDeliveryProfileConflictError(
                    "Onboarding cannot overwrite saved address values."
                )
        else:
            await self._add_address_locked(
                connection,
                tenant_id,
                current["id"],
                address_label,
                delivery_address,
                True,
            )
        row = await connection.fetchrow(
            """
            UPDATE saved_delivery_profiles
            SET customer_name=$2, phone_number=$3, phone_verified=FALSE,
                onboarding_status='COMPLETED', profile_consent_version=$4,
                profile_consented_at=$5, onboarding_request_id=$6, updated_at=now()
            WHERE id=$1
            RETURNING id, tenant_id, channel, channel_customer_id, customer_name,
                      phone_number, phone_verified, onboarding_status,
                      profile_consent_version, profile_consented_at,
                      onboarding_request_id, created_at, updated_at
            """,
            current["id"],
            customer_name,
            phone_number,
            consent_version,
            consented_at,
            request_id,
        )
        return self._profile(row)

    async def save_profile_details(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str,
        customer_name: str | None,
        phone_number: str | None,
    ) -> SavedDeliveryProfile:
        profile, _ = await self.save_details(
            tenant_id,
            channel,
            channel_customer_id,
            customer_name,
            phone_number,
            None,
            None,
            False,
        )
        return profile

    async def save_details(
        self,
        tenant_id: UUID,
        channel: ChannelName,
        channel_customer_id: str,
        customer_name: str | None,
        phone_number: str | None,
        address_label: str | None,
        delivery_address: str | None,
        set_as_default: bool,
        expected_profile_values: tuple[str | None, str | None] | None = None,
        expect_profile_absent: bool = False,
    ) -> tuple[SavedDeliveryProfile, SavedDeliveryAddress | None]:
        if self._connection is None:
            try:
                async with (
                    self._pool.pool.acquire() as connection,
                    connection.transaction(),
                ):
                    return await self._with(connection).save_details(
                        tenant_id,
                        channel,
                        channel_customer_id,
                        customer_name,
                        phone_number,
                        address_label,
                        delivery_address,
                        set_as_default,
                        expected_profile_values,
                        expect_profile_absent,
                    )
            except (
                SavedDeliveryProfileConflictError,
                SavedDeliveryAddressNotFoundError,
                StaleSavedDeliveryAddressError,
            ):
                raise
            except asyncpg.PostgresError as error:
                raise SavedDeliveryPersistenceError(
                    "Saved delivery details are temporarily unavailable."
                ) from error

        connection = self._connection
        insert_result = await connection.execute(
            """
            INSERT INTO saved_delivery_profiles (
                id, tenant_id, channel, channel_customer_id,
                customer_name, phone_number, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, NULL, NULL, now(), now())
            ON CONFLICT (tenant_id, channel, channel_customer_id) DO NOTHING
            """,
            uuid4(),
            tenant_id,
            channel.value,
            channel_customer_id,
        )
        current = await connection.fetchrow(
            """
            SELECT id, tenant_id, channel, channel_customer_id, customer_name,
                   phone_number, phone_verified, onboarding_status,
                   profile_consent_version, profile_consented_at,
                   onboarding_request_id, created_at, updated_at
            FROM saved_delivery_profiles
            WHERE tenant_id = $1 AND channel = $2 AND channel_customer_id = $3
            FOR UPDATE
            """,
            tenant_id,
            channel.value,
            channel_customer_id,
        )
        if current is None:
            raise SavedDeliveryPersistenceError(
                "Saved delivery profile was unavailable."
            )
        inserted = insert_result.endswith(" 1")
        if (
            expect_profile_absent
            and not inserted
            and (
                (
                    customer_name is not None
                    and current["customer_name"] not in {None, customer_name}
                )
                or (
                    phone_number is not None
                    and current["phone_number"] not in {None, phone_number}
                )
            )
        ):
            raise SavedDeliveryProfileConflictError(
                "A profile was created concurrently with different values."
            )
        if (
            expected_profile_values is not None
            and (current["customer_name"], current["phone_number"])
            != expected_profile_values
        ):
            raise SavedDeliveryProfileConflictError(
                "Saved profile values changed before confirmation."
            )
        next_name = (
            customer_name if customer_name is not None else current["customer_name"]
        )
        next_phone = (
            phone_number if phone_number is not None else current["phone_number"]
        )
        row = await connection.fetchrow(
            """
            UPDATE saved_delivery_profiles
            SET customer_name = $2, phone_number = $3, updated_at = now()
            WHERE id = $1
            RETURNING id, tenant_id, channel, channel_customer_id, customer_name,
                      phone_number, phone_verified, onboarding_status,
                      profile_consent_version, profile_consented_at,
                      onboarding_request_id, created_at, updated_at
            """,
            current["id"],
            next_name,
            next_phone,
        )
        address = None
        if address_label is not None and delivery_address is not None:
            address = await self._add_address_locked(
                connection,
                tenant_id,
                current["id"],
                address_label,
                delivery_address,
                set_as_default,
            )
        return self._profile(row), address

    async def list_addresses(
        self, tenant_id: UUID, profile_id: UUID
    ) -> tuple[SavedDeliveryAddress, ...]:
        if self._connection is None:
            try:
                async with self._pool.pool.acquire() as connection:
                    return await self._with(connection).list_addresses(
                        tenant_id, profile_id
                    )
            except asyncpg.PostgresError as error:
                raise SavedDeliveryPersistenceError(
                    "Saved addresses are temporarily unavailable."
                ) from error
        rows = await self._connection.fetch(
            """
            SELECT address.id, address.profile_id, address.label,
                   address.delivery_address, address.is_default, address.version,
                   address.created_at, address.updated_at
            FROM saved_delivery_addresses AS address
            JOIN saved_delivery_profiles AS profile ON profile.id = address.profile_id
            WHERE profile.tenant_id = $1 AND profile.id = $2
            ORDER BY address.is_default DESC, address.created_at, address.id
            """,
            tenant_id,
            profile_id,
        )
        return tuple(self._address(row) for row in rows)

    async def get_address(
        self, tenant_id: UUID, profile_id: UUID, address_id: UUID
    ) -> SavedDeliveryAddress | None:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await self._with(connection).get_address(
                    tenant_id, profile_id, address_id
                )
        row = await self._connection.fetchrow(
            """
            SELECT address.id, address.profile_id, address.label,
                   address.delivery_address, address.is_default, address.version,
                   address.created_at, address.updated_at
            FROM saved_delivery_addresses AS address
            JOIN saved_delivery_profiles AS profile ON profile.id = address.profile_id
            WHERE profile.tenant_id = $1 AND profile.id = $2 AND address.id = $3
            """,
            tenant_id,
            profile_id,
            address_id,
        )
        return self._address(row) if row is not None else None

    async def add_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        label: str,
        delivery_address: str,
        set_as_default: bool,
    ) -> SavedDeliveryAddress:
        if self._connection is None:
            try:
                async with (
                    self._pool.pool.acquire() as connection,
                    connection.transaction(),
                ):
                    return await self._with(connection).add_address(
                        tenant_id, profile_id, label, delivery_address, set_as_default
                    )
            except SavedDeliveryAddressNotFoundError:
                raise
            except asyncpg.PostgresError as error:
                raise SavedDeliveryPersistenceError(
                    "Saved address is temporarily unavailable."
                ) from error
        return await self._add_address_locked(
            self._connection,
            tenant_id,
            profile_id,
            label,
            delivery_address,
            set_as_default,
        )

    async def update_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        address_id: UUID,
        expected_version: int,
        label: str | None,
        delivery_address: str | None,
    ) -> SavedDeliveryAddress:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await self._with(connection).update_address(
                    tenant_id,
                    profile_id,
                    address_id,
                    expected_version,
                    label,
                    delivery_address,
                )
        row = await self._connection.fetchrow(
            """
            UPDATE saved_delivery_addresses AS address
            SET label = COALESCE($5, address.label),
                delivery_address = COALESCE($6, address.delivery_address),
                version = address.version + 1,
                updated_at = now()
            FROM saved_delivery_profiles AS profile
            WHERE address.id = $3 AND address.profile_id = $2
              AND profile.id = address.profile_id AND profile.tenant_id = $1
              AND address.version = $4
              AND (COALESCE($5, address.label), COALESCE($6, address.delivery_address))
                  IS DISTINCT FROM (address.label, address.delivery_address)
            RETURNING address.id, address.profile_id, address.label,
                      address.delivery_address, address.is_default, address.version,
                      address.created_at, address.updated_at
            """,
            tenant_id,
            profile_id,
            address_id,
            expected_version,
            label,
            delivery_address,
        )
        if row is not None:
            return self._address(row)
        current = await self.get_address(tenant_id, profile_id, address_id)
        if current is None:
            raise SavedDeliveryAddressNotFoundError("Saved address was not found.")
        if current.version != expected_version:
            raise StaleSavedDeliveryAddressError("Saved address version is stale.")
        raise ValueError("The saved address values are unchanged.")

    async def delete_address(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        address_id: UUID,
        expected_version: int,
    ) -> None:
        if self._connection is None:
            async with self._pool.pool.acquire() as connection:
                return await self._with(connection).delete_address(
                    tenant_id, profile_id, address_id, expected_version
                )
        deleted = await self._connection.fetchval(
            """
            DELETE FROM saved_delivery_addresses AS address
            USING saved_delivery_profiles AS profile
            WHERE address.id = $3 AND address.profile_id = $2
              AND profile.id = address.profile_id AND profile.tenant_id = $1
              AND address.version = $4
            RETURNING address.id
            """,
            tenant_id,
            profile_id,
            address_id,
            expected_version,
        )
        if deleted is not None:
            return
        current = await self.get_address(tenant_id, profile_id, address_id)
        if current is None:
            raise SavedDeliveryAddressNotFoundError("Saved address was not found.")
        raise StaleSavedDeliveryAddressError("Saved address version is stale.")

    async def set_default_address(
        self, tenant_id: UUID, profile_id: UUID, address_id: UUID
    ) -> SavedDeliveryAddress:
        if self._connection is None:
            try:
                async with (
                    self._pool.pool.acquire() as connection,
                    connection.transaction(),
                ):
                    return await self._with(connection).set_default_address(
                        tenant_id, profile_id, address_id
                    )
            except SavedDeliveryAddressNotFoundError:
                raise
            except asyncpg.PostgresError as error:
                raise SavedDeliveryPersistenceError(
                    "Saved address is temporarily unavailable."
                ) from error
        connection = self._connection
        profile = await connection.fetchval(
            """
            SELECT id FROM saved_delivery_profiles
            WHERE id = $1 AND tenant_id = $2 FOR UPDATE
            """,
            profile_id,
            tenant_id,
        )
        if profile is None:
            raise SavedDeliveryAddressNotFoundError("Saved address was not found.")
        rows = await connection.fetch(
            """
            SELECT id, is_default FROM saved_delivery_addresses
            WHERE profile_id = $1 ORDER BY id FOR UPDATE
            """,
            profile_id,
        )
        target = next((row for row in rows if row["id"] == address_id), None)
        if target is None:
            raise SavedDeliveryAddressNotFoundError("Saved address was not found.")
        if target["is_default"]:
            result = await self.get_address(tenant_id, profile_id, address_id)
            if result is None:
                raise SavedDeliveryAddressNotFoundError("Saved address was not found.")
            return result
        await connection.execute(
            """
            UPDATE saved_delivery_addresses
            SET is_default = FALSE, version = version + 1, updated_at = now()
            WHERE profile_id = $1 AND is_default = TRUE
            """,
            profile_id,
        )
        row = await connection.fetchrow(
            """
            UPDATE saved_delivery_addresses
            SET is_default = TRUE, version = version + 1, updated_at = now()
            WHERE profile_id = $1 AND id = $2
            RETURNING id, profile_id, label, delivery_address, is_default,
                      version, created_at, updated_at
            """,
            profile_id,
            address_id,
        )
        return self._address(row)

    async def _add_address_locked(
        self,
        connection: asyncpg.Connection,
        tenant_id: UUID,
        profile_id: UUID,
        label: str,
        delivery_address: str,
        set_as_default: bool,
    ) -> SavedDeliveryAddress:
        profile = await connection.fetchval(
            """
            SELECT id FROM saved_delivery_profiles
            WHERE id = $1 AND tenant_id = $2 FOR UPDATE
            """,
            profile_id,
            tenant_id,
        )
        if profile is None:
            raise SavedDeliveryAddressNotFoundError("Saved profile was not found.")
        if set_as_default:
            await connection.execute(
                """
                UPDATE saved_delivery_addresses
                SET is_default = FALSE, version = version + 1, updated_at = now()
                WHERE profile_id = $1 AND is_default = TRUE
                """,
                profile_id,
            )
        row = await connection.fetchrow(
            """
            INSERT INTO saved_delivery_addresses (
                id, profile_id, label, delivery_address, is_default,
                version, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, $5, 1, now(), now())
            RETURNING id, profile_id, label, delivery_address, is_default,
                      version, created_at, updated_at
            """,
            uuid4(),
            profile_id,
            label,
            delivery_address,
            set_as_default,
        )
        return self._address(row)

    def _with(
        self, connection: asyncpg.Connection
    ) -> PostgresSavedDeliveryDetailsRepository:
        return PostgresSavedDeliveryDetailsRepository(self._pool, connection)

    @staticmethod
    def _profile(row: asyncpg.Record) -> SavedDeliveryProfile:
        return SavedDeliveryProfile(
            id=row["id"],
            tenant_id=row["tenant_id"],
            channel=ChannelName(row["channel"]),
            channel_customer_id=row["channel_customer_id"],
            customer_name=row["customer_name"],
            phone_number=row["phone_number"],
            phone_verified=row["phone_verified"],
            onboarding_status=row["onboarding_status"],
            profile_consent_version=row["profile_consent_version"],
            profile_consented_at=row["profile_consented_at"],
            onboarding_request_id=row["onboarding_request_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _address(row: asyncpg.Record) -> SavedDeliveryAddress:
        return SavedDeliveryAddress(
            id=row["id"],
            profile_id=row["profile_id"],
            label=row["label"],
            delivery_address=row["delivery_address"],
            is_default=row["is_default"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
