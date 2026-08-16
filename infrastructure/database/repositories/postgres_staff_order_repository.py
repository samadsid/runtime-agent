from __future__ import annotations

from datetime import datetime
from uuid import UUID

from commerce.models import (
    StaffDashboardCounts,
    StaffOrderDetails,
    StaffOrderFilters,
    StaffOrderItem,
    StaffOrderListItem,
    StaffOrderTimelineEntry,
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
            return StaffOrderDetails(
                order_id=order.id,
                order_reference=str(order.id),
                status=order.status.value,
                payment_method=order.payment_method.value,
                customer_name=order.customer_name,
                phone_number=order.phone_number,
                delivery_address=order.delivery_address,
                created_at=order.created_at,
                confirmed_at=order.confirmed_at,
                updated_at=order.updated_at,
                version=order.version,
                items=tuple(
                    StaffOrderItem(
                        product_name=item.product_name,
                        unit=item.unit,
                        unit_price=item.unit_price,
                        currency=item.currency,
                        quantity=item.quantity,
                        line_total=item.unit_price * item.quantity,
                    )
                    for item in order.items
                ),
                timeline=tuple(
                    StaffOrderTimelineEntry(
                        from_status=entry.from_status.value if entry.from_status else None,
                        to_status=entry.to_status.value,
                        actor_type=entry.actor_type,
                        reason=entry.reason,
                        created_at=entry.created_at,
                    )
                    for entry in order.status_history
                ),
                total=found["total"],
                currency=found["currency"],
                payment_status=payment_status,
            )

    async def dashboard_counts(self, tenant_id: UUID) -> StaffDashboardCounts:
        rows = await self._pool.pool.fetch(
            """SELECT o.status,COUNT(*) AS count
               FROM orders o JOIN carts c ON c.id=o.source_cart_id AND c.tenant_id=$1
               WHERE o.status = ANY($2::text[])
               GROUP BY o.status""",
            tenant_id, ["CONFIRMED", "PREPARING", "OUT_FOR_DELIVERY"],
        )
        counts = {row["status"]: row["count"] for row in rows}
        return StaffDashboardCounts(
            confirmed=counts.get("CONFIRMED", 0),
            preparing=counts.get("PREPARING", 0),
            out_for_delivery=counts.get("OUT_FOR_DELIVERY", 0),
        )

    async def oldest_confirmed_orders(
        self, tenant_id: UUID, limit: int = 5
    ) -> tuple[StaffOrderListItem, ...]:
        rows = await self._pool.pool.fetch(
            """SELECT o.id,o.status,o.payment_method,o.customer_name,o.phone_number,
                      o.created_at,o.updated_at,o.version,
                      COALESCE(SUM(i.unit_price*i.quantity),0) total,
                      COALESCE(MIN(i.currency),'INR') currency
               FROM orders o
               JOIN carts c ON c.id=o.source_cart_id AND c.tenant_id=$1
               LEFT JOIN order_items i ON i.order_id=o.id
               WHERE o.status='CONFIRMED'
               GROUP BY o.id
               ORDER BY o.created_at ASC,o.id ASC LIMIT $2""",
            tenant_id, limit,
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
