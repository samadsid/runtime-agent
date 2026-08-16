from __future__ import annotations

from datetime import datetime
from uuid import UUID

from commerce.models import (
    StaffOrderDetails,
    StaffOrderFilters,
    StaffOrderListItem,
)
from infrastructure.database import DatabasePool

from .postgres_order_repository import PostgresOrderRepository


def mask_phone(value: str) -> str:
    stripped = value.strip()
    if len(stripped) <= 4:
        return "*" * len(stripped)
    return "*" * (len(stripped) - 4) + stripped[-4:]


class PostgresStaffOrderRepository:
    def __init__(self, pool: DatabasePool) -> None:
        self._pool = pool

    async def list_orders(
        self, tenant_id: UUID, filters: StaffOrderFilters, limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> tuple[StaffOrderListItem, ...]:
        rows = await self._pool.pool.fetch(
            """SELECT o.id,o.status,o.payment_method,o.customer_name,o.phone_number,
                      o.created_at,o.updated_at,o.version,
                      COALESCE(SUM(i.unit_price*i.quantity),0) total,
                      COALESCE(MIN(i.currency),'INR') currency
               FROM orders o
               JOIN carts c ON c.id=o.source_cart_id AND c.tenant_id=$1
               LEFT JOIN order_items i ON i.order_id=o.id
               WHERE ($2::text IS NULL OR o.status=$2)
                 AND ($3::timestamptz IS NULL OR o.created_at >= $3)
                 AND ($4::timestamptz IS NULL OR o.created_at <= $4)
                 AND ($5::uuid IS NULL OR o.id=$5)
                 AND ($6::timestamptz IS NULL OR (o.created_at,o.id) < ($6,$7))
               GROUP BY o.id
               ORDER BY o.created_at DESC,o.id DESC LIMIT $8""",
            tenant_id, filters.status, filters.created_from, filters.created_to,
            filters.order_reference, cursor[0] if cursor else None,
            cursor[1] if cursor else None, limit,
        )
        return tuple(
            StaffOrderListItem(
                order_id=row["id"], order_reference=str(row["id"]), status=row["status"],
                payment_method=row["payment_method"], total=row["total"],
                currency=row["currency"], customer_name=row["customer_name"],
                masked_phone_number=mask_phone(row["phone_number"]),
                created_at=row["created_at"], updated_at=row["updated_at"],
                version=row["version"],
            ) for row in rows
        )

    async def get_order(self, tenant_id: UUID, order_id: UUID) -> StaffOrderDetails | None:
        async with self._pool.pool.acquire() as connection:
            found = await connection.fetchrow(
                """SELECT o.id,COALESCE(SUM(i.unit_price*i.quantity),0) total,
                          COALESCE(MIN(i.currency),'INR') currency
                   FROM orders o JOIN carts c ON c.id=o.source_cart_id AND c.tenant_id=$1
                   LEFT JOIN order_items i ON i.order_id=o.id
                   WHERE o.id=$2 GROUP BY o.id""",
                tenant_id, order_id,
            )
            if found is None:
                return None
            order = await PostgresOrderRepository(self._pool, connection).get_by_id(
                order_id
            )
            payment_status = await connection.fetchval(
                """SELECT status FROM payment_attempts WHERE tenant_id=$1 AND order_id=$2
                   ORDER BY created_at DESC,id DESC LIMIT 1""",
                tenant_id, order_id,
            )
            assert order is not None
            return StaffOrderDetails(order=order, total=found["total"],
                                     currency=found["currency"], payment_status=payment_status)
