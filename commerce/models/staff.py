from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .fulfilment import FulfilmentActorType


class StaffStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class StaffRole(str, Enum):
    ADMIN = "ADMIN"
    FULFILMENT_STAFF = "FULFILMENT_STAFF"


class StaffAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    email: str
    display_name: str
    status: StaffStatus
    created_at: datetime
    updated_at: datetime


class StaffTenantMembership(BaseModel):
    model_config = ConfigDict(frozen=True)

    staff_id: UUID
    tenant_id: UUID
    role: StaffRole
    active: bool
    created_at: datetime
    updated_at: datetime


class StaffRequestContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    staff_id: UUID
    tenant_id: UUID
    role: StaffRole
    request_id: str


class StaffOrderFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    order_reference: UUID | None = None


class StaffOrderListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    order_reference: str
    status: str
    payment_method: str
    total: Decimal
    currency: str
    customer_name: str
    masked_phone_number: str
    created_at: datetime
    updated_at: datetime
    version: int


class StaffOrderPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[StaffOrderListItem, ...]
    next_cursor: str | None = None


class StaffOrderItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_name: str
    unit: str
    unit_price: Decimal
    currency: str
    quantity: Decimal
    line_total: Decimal


class StaffOrderTimelineEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_status: str | None
    to_status: str
    actor_type: FulfilmentActorType
    reason: str | None
    created_at: datetime


class StaffPermittedOrderAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_status: str
    requires_reason: bool = False


class StaffOrderDetails(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    order_reference: str
    status: str
    payment_method: str
    customer_name: str
    phone_number: str
    delivery_address: str
    created_at: datetime
    confirmed_at: datetime | None
    updated_at: datetime | None
    version: int
    items: tuple[StaffOrderItem, ...]
    timeline: tuple[StaffOrderTimelineEntry, ...]
    total: Decimal
    currency: str
    payment_status: str | None = None
    permitted_actions: tuple[StaffPermittedOrderAction, ...] = ()


class StaffDashboardCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    confirmed: int = 0
    preparing: int = 0
    out_for_delivery: int = 0


class StaffDashboardSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    counts: StaffDashboardCounts
    oldest_confirmed_orders: tuple[StaffOrderListItem, ...] = ()
