from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from commerce.models import DeliveryZone, ProductStatus

Password = Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class StaffLoginRequest(BaseModel):
    email: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=320)
    ]
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
    reason: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=500)
    ] = None


class StaffTransitionResponse(BaseModel):
    order_id: UUID
    status: str
    version: int
    transitioned_at: datetime


class CreateProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
    ]
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    category_id: UUID | None = None
    price: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)
    ]
    unit: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)
    ]
    status: ProductStatus = ProductStatus.INACTIVE
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int = Field(default=0, ge=0)


class UpdateProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=64),
    ] = None
    name: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    ] = None
    category_id: UUID | None = None
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=3, max_length=3)
    ] = None
    unit: Annotated[
        str | None,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=32),
    ] = None
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int | None = Field(default=None, ge=0)


class ProductStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProductStatus
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


class InventoryAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movement_type: str
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]


def _validate_geojson(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Boundary must be a GeoJSON Polygon or MultiPolygon.")
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("Boundary coordinates are required.")

    def visit(node: object, depth: int = 0) -> None:
        if depth > 5 or not isinstance(node, list) or not node:
            raise ValueError("Invalid GeoJSON coordinate nesting.")
        if all(
            isinstance(item, (int, float, Decimal)) and not isinstance(item, bool)
            for item in node
        ):
            if len(node) != 2:
                raise ValueError("Only two-dimensional coordinates are supported.")
            longitude, latitude = (Decimal(str(item)) for item in node)
            if (
                not longitude.is_finite()
                or not latitude.is_finite()
                or not Decimal(-180) <= longitude <= Decimal(180)
                or not Decimal(-90) <= latitude <= Decimal(90)
            ):
                raise ValueError("GeoJSON coordinate is outside WGS84 bounds.")
            return
        for child in node:
            visit(child, depth + 1)

    visit(coordinates)
    if set(value) - {"type", "coordinates"}:
        raise ValueError("Unsupported GeoJSON members.")
    return value


class CreateDeliveryZoneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    priority: int = Field(default=100, ge=0, le=1_000_000)
    boundary: dict[str, Any]

    _boundary = field_validator("boundary")(_validate_geojson)


class UpdateDeliveryZoneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    priority: int | None = Field(default=None, ge=0, le=1_000_000)
    boundary: dict[str, Any] | None = None

    @field_validator("boundary")
    @classmethod
    def validate_boundary(cls, value):
        return _validate_geojson(value) if value is not None else None


class DeliveryZonePointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    latitude: Decimal = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: Decimal = Field(ge=-180, le=180, allow_inf_nan=False)


class DeliveryZonePage(BaseModel):
    items: tuple[DeliveryZone, ...]
    next_cursor: str | None = None


class DeliveryZonePointResponse(BaseModel):
    serviceable: bool
    zone_name: str | None = None
    zone_version: int | None = None
