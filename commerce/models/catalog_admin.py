from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .product import ProductStatus


class InventoryMovementType(str, Enum):
    OPENING_BALANCE = "OPENING_BALANCE"
    RECEIPT = "RECEIPT"
    POSITIVE_CORRECTION = "POSITIVE_CORRECTION"
    NEGATIVE_CORRECTION = "NEGATIVE_CORRECTION"
    DAMAGE = "DAMAGE"
    WASTAGE = "WASTAGE"
    RESERVATION = "RESERVATION"
    RELEASE = "RELEASE"
    CONSUMPTION = "CONSUMPTION"


class ManualInventoryMovementType(str, Enum):
    RECEIPT = "RECEIPT"
    POSITIVE_CORRECTION = "POSITIVE_CORRECTION"
    NEGATIVE_CORRECTION = "NEGATIVE_CORRECTION"
    DAMAGE = "DAMAGE"
    WASTAGE = "WASTAGE"


class StockState(str, Enum):
    LOW = "LOW"
    OUT = "OUT"
    AVAILABLE = "AVAILABLE"


class AdminProduct(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    category_id: UUID | None
    category_name: str | None = None
    price: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str
    unit: str
    status: ProductStatus
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int = Field(ge=0)
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ProductWithInventory(BaseModel):
    model_config = ConfigDict(frozen=True)

    product: AdminProduct
    on_hand_quantity: Decimal
    reserved_quantity: Decimal
    sellable_quantity: Decimal
    inventory_version: int
    inventory_updated_at: datetime
    stock_states: tuple[StockState, ...] = ()
    permitted_actions: tuple[str, ...] = ()


class AdminProductPage(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: tuple[ProductWithInventory, ...]
    next_cursor: str | None = None


class CatalogOption(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    name: str


class CatalogOptions(BaseModel):
    model_config = ConfigDict(frozen=True)
    categories: tuple[CatalogOption, ...]
    currencies: tuple[str, ...]
    units: tuple[str, ...]


class InventoryMovement(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    tenant_id: UUID
    product_id: UUID
    movement_type: InventoryMovementType
    quantity: Decimal
    on_hand_delta: Decimal
    reserved_delta: Decimal
    on_hand_before: Decimal
    on_hand_after: Decimal
    reserved_before: Decimal
    reserved_after: Decimal
    reference_type: str | None = None
    reference_id: UUID | None = None
    reason: str
    actor_type: str
    actor_id: UUID | None = None
    created_at: datetime


class InventoryMovementPage(BaseModel):
    model_config = ConfigDict(frozen=True)
    items: tuple[InventoryMovement, ...]
    next_cursor: str | None = None


class InventoryAdjustmentResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    balance: ProductWithInventory
    movement: InventoryMovement
    idempotent: bool = False


class InventorySummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    active_products: int
    low_stock_products: int
    out_of_stock_products: int
    inactive_products: int
    oldest_low_stock_products: tuple[ProductWithInventory, ...] = ()
