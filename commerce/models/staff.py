from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .order import Order


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


class StaffOrderDetails(BaseModel):
    model_config = ConfigDict(frozen=True)

    order: Order
    total: Decimal
    currency: str
    payment_status: str | None = None
    permitted_actions: tuple[str, ...] = ()
