from __future__ import annotations

import base64
import json
from datetime import datetime
from uuid import UUID

from commerce.models import (
    OrderStatus,
    StaffDashboardSummary,
    StaffOrderDetails,
    StaffOrderFilters,
    StaffOrderPage,
    StaffPermittedOrderAction,
    StaffRequestContext,
    StaffRole,
)
from commerce.services import FulfilmentService
from infrastructure.database.repositories.postgres_staff_order_repository import (
    PostgresStaffOrderRepository,
)


class InvalidStaffOrderCursorError(ValueError):
    pass


def encode_cursor(created_at: datetime, order_id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(order_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[datetime, UUID] | None:
    if value is None:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        timestamp, order_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None:
            raise ValueError
        return parsed, UUID(order_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise InvalidStaffOrderCursorError("Invalid order cursor.") from error


class StaffOrderQueryService:
    def __init__(self, repository: PostgresStaffOrderRepository) -> None:
        self._repository = repository

    async def list_orders(self, context: StaffRequestContext, filters: StaffOrderFilters,
                          limit: int, cursor: str | None) -> StaffOrderPage:
        position = decode_cursor(cursor)
        items = await self._repository.list_orders(
            context.tenant_id, filters, limit + 1, position
        )
        has_more = len(items) > limit
        visible = items[:limit]
        next_cursor = (
            encode_cursor(visible[-1].created_at, visible[-1].order_id)
            if has_more and visible else None
        )
        return StaffOrderPage(items=visible, next_cursor=next_cursor)

    async def get_order(self, context: StaffRequestContext,
                        order_id: UUID) -> StaffOrderDetails | None:
        details = await self._repository.get_order(context.tenant_id, order_id)
        if details is None:
            return None
        allowed = tuple(
            StaffPermittedOrderAction(
                target_status=status.value,
                requires_reason=status == OrderStatus.CANCELLED,
            )
            for status in OrderStatus
            if FulfilmentService.is_transition_allowed(OrderStatus(details.status), status)
        )
        if context.role != StaffRole.ADMIN:
            allowed = tuple(
                value for value in allowed
                if value.target_status != OrderStatus.CANCELLED.value
            )
        return details.model_copy(
            update={"permitted_actions": allowed}
        )

    async def dashboard_summary(self, context: StaffRequestContext) -> StaffDashboardSummary:
        counts = await self._repository.dashboard_counts(context.tenant_id)
        queue = await self._repository.oldest_confirmed_orders(context.tenant_id, 5)
        return StaffDashboardSummary(counts=counts, oldest_confirmed_orders=queue)
