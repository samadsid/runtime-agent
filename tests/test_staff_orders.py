from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from commerce.models import (
    OrderStatus,
    StaffDashboardCounts,
    StaffOrderDetails,
    StaffRequestContext,
    StaffRole,
)
from services.staff_orders import StaffOrderQueryService


def details(status: OrderStatus = OrderStatus.CONFIRMED) -> StaffOrderDetails:
    now = datetime.now(timezone.utc)
    order_id = uuid4()
    return StaffOrderDetails(
        order_id=order_id,
        order_reference=str(order_id),
        status=status.value,
        payment_method="CASH_ON_DELIVERY",
        customer_name="Customer",
        phone_number="+919999999999",
        delivery_address="Delivery address",
        created_at=now,
        confirmed_at=now,
        updated_at=now,
        version=1,
        items=(),
        timeline=(),
        total=Decimal("10.00"),
        currency="INR",
    )


class Repository:
    def __init__(self) -> None:
        self.details = details()

    async def get_order(self, tenant_id, order_id):
        del tenant_id
        return self.details if order_id == self.details.order_id else None

    async def dashboard_counts(self, tenant_id):
        del tenant_id
        return StaffDashboardCounts(confirmed=1)

    async def oldest_confirmed_orders(self, tenant_id, limit):
        del tenant_id
        assert limit == 5
        return ()


def context(role: StaffRole) -> StaffRequestContext:
    return StaffRequestContext(
        staff_id=uuid4(), tenant_id=uuid4(), role=role, request_id="request"
    )


@pytest.mark.asyncio
async def test_permitted_actions_are_typed_and_role_aware() -> None:
    repository = Repository()
    service = StaffOrderQueryService(repository)  # type: ignore[arg-type]

    admin = await service.get_order(context(StaffRole.ADMIN), repository.details.order_id)
    staff = await service.get_order(
        context(StaffRole.FULFILMENT_STAFF), repository.details.order_id
    )

    assert admin is not None and staff is not None
    assert [(action.target_status, action.requires_reason) for action in admin.permitted_actions] == [
        ("PREPARING", False),
        ("CANCELLED", True),
    ]
    assert [action.target_status for action in staff.permitted_actions] == ["PREPARING"]


@pytest.mark.asyncio
async def test_dashboard_summary_uses_bounded_oldest_queue() -> None:
    service = StaffOrderQueryService(Repository())  # type: ignore[arg-type]
    summary = await service.dashboard_summary(context(StaffRole.ADMIN))

    assert summary.counts.confirmed == 1
    assert summary.oldest_confirmed_orders == ()
