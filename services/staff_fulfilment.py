from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
from pydantic import BaseModel, ConfigDict

from commerce.models import (
    FulfilmentActor,
    FulfilmentActorType,
    OrderStatus,
    StaffRequestContext,
    StaffRole,
)
from commerce.repositories import InvalidOrderTransitionError, OrderNotFoundError
from commerce.services import FulfilmentService
from infrastructure.database import DatabasePool
from infrastructure.database.repositories.postgres_inventory_repository import (
    PostgresInventoryRepository,
)
from infrastructure.database.repositories.postgres_order_repository import (
    PostgresOrderRepository,
)

logger = logging.getLogger(__name__)


class StaleOrderVersionError(ValueError):
    def __init__(self, version: int, status: OrderStatus) -> None:
        self.version = version
        self.status = status


class IdempotencyKeyConflictError(ValueError):
    pass


class StaffTransitionUnavailableError(RuntimeError):
    pass


class StaffTransitionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    status: OrderStatus
    version: int
    transitioned_at: datetime
    idempotent: bool = False


class StaffFulfilmentService:
    def __init__(self, pool: DatabasePool, retention_hours: int) -> None:
        self._pool = pool
        self._retention_hours = retention_hours

    async def transition_order(
        self, *, context: StaffRequestContext, order_id: UUID, expected_version: int,
        target_status: OrderStatus, reason: str | None, idempotency_key: str,
        request_hash: str,
    ) -> StaffTransitionResult:
        for attempt in range(3):
            try:
                async with self._pool.pool.acquire() as connection, connection.transaction():
                    return await self._transition(
                        connection, context, order_id, expected_version, target_status,
                        reason, idempotency_key, request_hash,
                    )
            except asyncpg.PostgresError as error:
                if error.sqlstate not in {"40P01", "40001"}:
                    raise
                if attempt == 2:
                    logger.error("Staff transition retry exhausted.", extra={"event": "staff_transition_retry_exhausted"})
                    raise StaffTransitionUnavailableError from error
                await asyncio.sleep(0.025 * (2**attempt))
        raise AssertionError("Retry loop did not finish.")

    async def _transition(
        self, connection: asyncpg.Connection, context: StaffRequestContext,
        order_id: UUID, expected_version: int, target_status: OrderStatus,
        reason: str | None, idempotency_key: str, request_hash: str,
    ) -> StaffTransitionResult:
        await connection.execute(
            """DELETE FROM staff_api_idempotency WHERE id IN (
                   SELECT id FROM staff_api_idempotency WHERE expires_at <= now()
                   ORDER BY expires_at LIMIT 100
               )"""
        )
        record_id = uuid4()
        inserted = await connection.fetchval(
            """INSERT INTO staff_api_idempotency
               (id,tenant_id,staff_id,idempotency_key,operation,request_hash,resource_id,
                created_at,expires_at)
               VALUES ($1,$2,$3,$4,'transition_order',$5,$6,now(),$7)
               ON CONFLICT (tenant_id,staff_id,idempotency_key) DO NOTHING RETURNING id""",
            record_id, context.tenant_id, context.staff_id, idempotency_key,
            request_hash, order_id,
            datetime.now(timezone.utc) + timedelta(hours=self._retention_hours),
        )
        if inserted is None:
            existing = await connection.fetchrow(
                """SELECT request_hash,response_body FROM staff_api_idempotency
                   WHERE tenant_id=$1 AND staff_id=$2 AND idempotency_key=$3""",
                context.tenant_id, context.staff_id, idempotency_key,
            )
            if existing is None or existing["request_hash"] != request_hash:
                raise IdempotencyKeyConflictError
            body = existing["response_body"]
            if body is None:
                raise StaffTransitionUnavailableError
            return StaffTransitionResult(
                order_id=UUID(body["order_id"]), status=OrderStatus(body["status"]),
                version=body["version"],
                transitioned_at=datetime.fromisoformat(body["transitioned_at"]),
                idempotent=True,
            )

        membership = await connection.fetchrow(
            """SELECT role FROM staff_tenant_memberships m
               JOIN staff_accounts a ON a.id=m.staff_id
               WHERE m.staff_id=$1 AND m.tenant_id=$2 AND m.active=true
                 AND a.status='ACTIVE'""",
            context.staff_id, context.tenant_id,
        )
        if membership is None:
            from services.staff_auth import StaffAccessDeniedError
            raise StaffAccessDeniedError
        role = StaffRole(membership["role"])
        if target_status == OrderStatus.CANCELLED and role != StaffRole.ADMIN:
            from services.staff_auth import StaffAccessDeniedError
            raise StaffAccessDeniedError

        current = await connection.fetchrow(
            """SELECT o.status,o.version FROM orders o
               JOIN carts c ON c.id=o.source_cart_id
               WHERE o.id=$1 AND c.tenant_id=$2 FOR UPDATE OF o""",
            order_id, context.tenant_id,
        )
        if current is None:
            raise OrderNotFoundError
        current_status = OrderStatus(current["status"])
        if current["version"] != expected_version:
            raise StaleOrderVersionError(current["version"], current_status)
        if not FulfilmentService.is_transition_allowed(current_status, target_status):
            raise InvalidOrderTransitionError

        inventory = PostgresInventoryRepository(self._pool, connection)
        if target_status == OrderStatus.CANCELLED:
            await inventory.release_for_order(order_id)
        elif target_status == OrderStatus.DELIVERED:
            await inventory.consume_for_order(order_id)
        order = await PostgresOrderRepository(self._pool, connection).transition_status(
            order_id, target_status,
            FulfilmentActor(actor_id=context.staff_id, actor_type=FulfilmentActorType.STAFF),
            reason,
        )
        transitioned_at = order.updated_at or datetime.now(timezone.utc)
        response = {
            "order_id": str(order.id), "status": order.status.value,
            "version": order.version, "transitioned_at": transitioned_at.isoformat(),
        }
        await connection.execute(
            """UPDATE staff_api_idempotency SET response_status=200,response_body=$2::jsonb
               WHERE id=$1""",
            record_id, json.dumps(response),
        )
        return StaffTransitionResult(
            order_id=order.id, status=order.status, version=order.version,
            transitioned_at=transitioned_at,
        )
