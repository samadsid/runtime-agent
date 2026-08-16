from __future__ import annotations

from uuid import UUID, uuid4

import asyncpg

from commerce.models import (
    StaffAccount,
    StaffRole,
    StaffStatus,
    StaffTenantMembership,
)
from infrastructure.database import DatabasePool


class StaffIdentityConflictError(ValueError):
    pass


class PostgresStaffRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def get_credentials(self, email_normalized: str) -> tuple[StaffAccount, str] | None:
        row = await self._pool.pool.fetchrow(
            """SELECT id,email_normalized,display_name,password_hash,status,created_at,updated_at
               FROM staff_accounts WHERE email_normalized=$1""",
            email_normalized,
        )
        if row is None:
            return None
        return self._account(row), row["password_hash"]

    async def get_account(self, staff_id: UUID) -> StaffAccount | None:
        row = await self._pool.pool.fetchrow(
            """SELECT id,email_normalized,display_name,status,created_at,updated_at
               FROM staff_accounts WHERE id=$1""",
            staff_id,
        )
        return self._account(row) if row else None

    async def get_membership(
        self, staff_id: UUID, tenant_id: UUID
    ) -> StaffTenantMembership | None:
        row = await self._pool.pool.fetchrow(
            """SELECT staff_id,tenant_id,role,active,created_at,updated_at
               FROM staff_tenant_memberships WHERE staff_id=$1 AND tenant_id=$2""",
            staff_id,
            tenant_id,
        )
        return self._membership(row) if row else None

    async def list_active_memberships(
        self, staff_id: UUID
    ) -> tuple[StaffTenantMembership, ...]:
        rows = await self._pool.pool.fetch(
            """SELECT staff_id,tenant_id,role,active,created_at,updated_at
               FROM staff_tenant_memberships WHERE staff_id=$1 AND active=true
               ORDER BY tenant_id""",
            staff_id,
        )
        return tuple(self._membership(row) for row in rows)

    async def bootstrap(
        self,
        *,
        email_normalized: str,
        display_name: str,
        password_hash: str,
        tenant_id: UUID,
        role: StaffRole,
    ) -> tuple[StaffAccount, StaffTenantMembership, bool]:
        async with self._pool.pool.acquire() as connection, connection.transaction():
            row = await connection.fetchrow(
                """SELECT id,email_normalized,display_name,password_hash,status,
                          created_at,updated_at
                   FROM staff_accounts WHERE email_normalized=$1 FOR UPDATE""",
                email_normalized,
            )
            created = row is None
            if row is None:
                staff_id = uuid4()
                row = await connection.fetchrow(
                    """INSERT INTO staff_accounts
                       (id,email_normalized,display_name,password_hash,status,created_at,updated_at)
                       VALUES ($1,$2,$3,$4,'ACTIVE',now(),now())
                       RETURNING id,email_normalized,display_name,password_hash,status,
                                 created_at,updated_at""",
                    staff_id,
                    email_normalized,
                    display_name,
                    password_hash,
                )
            elif row["display_name"] != display_name or row["status"] != "ACTIVE":
                raise StaffIdentityConflictError("Existing staff account differs.")
            membership = await connection.fetchrow(
                """SELECT staff_id,tenant_id,role,active,created_at,updated_at
                   FROM staff_tenant_memberships WHERE staff_id=$1 AND tenant_id=$2
                   FOR UPDATE""",
                row["id"],
                tenant_id,
            )
            if membership is None:
                membership = await connection.fetchrow(
                    """INSERT INTO staff_tenant_memberships
                       (staff_id,tenant_id,role,active,created_at,updated_at)
                       VALUES ($1,$2,$3,true,now(),now())
                       RETURNING staff_id,tenant_id,role,active,created_at,updated_at""",
                    row["id"],
                    tenant_id,
                    role.value,
                )
            elif membership["role"] != role.value or not membership["active"]:
                raise StaffIdentityConflictError("Existing membership differs.")
            return self._account(row), self._membership(membership), created

    @staticmethod
    def _account(row: asyncpg.Record) -> StaffAccount:
        return StaffAccount(
            id=row["id"], email=row["email_normalized"],
            display_name=row["display_name"], status=StaffStatus(row["status"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _membership(row: asyncpg.Record) -> StaffTenantMembership:
        return StaffTenantMembership(
            staff_id=row["staff_id"], tenant_id=row["tenant_id"],
            role=StaffRole(row["role"]), active=row["active"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
