from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from commerce.models import ProductStatus

Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class StaffLoginRequest(BaseModel):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)]
    password: Password


class StaffLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class StaffMembershipResponse(BaseModel):
    tenant_id: UUID
    role: str


class StaffMeResponse(BaseModel):
    staff_id: UUID
    display_name: str
    active_membership: StaffMembershipResponse
    memberships: tuple[StaffMembershipResponse, ...]


class StaffTransitionRequest(BaseModel):
    target_status: str
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None


class StaffTransitionResponse(BaseModel):
    order_id: UUID
    status: str
    version: int
    transitioned_at: datetime


class CreateProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    category_id: UUID | None = None
    price: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)]
    unit: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
    status: ProductStatus = ProductStatus.INACTIVE
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int = Field(default=0, ge=0)


class UpdateProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] = None
    name: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] = None
    category_id: UUID | None = None
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)] = None
    unit: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)] = None
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int | None = Field(default=None, ge=0)


class ProductStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProductStatus
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class InventoryAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movement_type: str
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
