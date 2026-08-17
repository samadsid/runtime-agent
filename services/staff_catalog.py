from __future__ import annotations

import json
import unicodedata
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from commerce.models import (
    AdminProductPage,
    CatalogOptions,
    InventoryAdjustmentResult,
    InventoryMovementPage,
    InventoryMovementType,
    InventorySummary,
    ManualInventoryMovementType,
    ProductStatus,
    ProductWithInventory,
    StaffRequestContext,
)
from infrastructure.database.repositories.postgres_catalog_admin_repository import (
    PostgresCatalogAdminRepository,
)


class CreateProductCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku: str
    name: str
    category_id: UUID | None = None
    price: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str
    unit: str
    status: ProductStatus = ProductStatus.INACTIVE
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int = Field(default=0, ge=0)


class UpdateProductCommand(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku: str | None = None
    name: str | None = None
    category_id: UUID | None = None
    price: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = None
    unit: str | None = None
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    display_order: int | None = Field(default=None, ge=0)


def normalize_sku(value: str) -> tuple[str, str]:
    display = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not display or len(display) > 64:
        raise ValueError("invalid SKU")
    return display, display.casefold()


class StaffCatalogService:
    def __init__(self, repository: PostgresCatalogAdminRepository, currencies: tuple[str, ...], units: tuple[str, ...]) -> None:
        self._repository = repository
        self._currencies = currencies
        self._units = units

    async def options(self, context: StaffRequestContext) -> CatalogOptions:
        return CatalogOptions(categories=await self._repository.list_options(context.tenant_id), currencies=self._currencies, units=self._units)

    async def list_products(self, context: StaffRequestContext, **filters) -> AdminProductPage:
        return await self._repository.list_products(context.tenant_id, **filters)

    async def get_product(self, context: StaffRequestContext, product_id: UUID) -> ProductWithInventory | None:
        return await self._repository.get_product(context.tenant_id, product_id)

    async def create_product(self, context: StaffRequestContext, command: CreateProductCommand, key: str) -> ProductWithInventory:
        values = self._create_values(command)
        return await self._repository.create_product(tenant_id=context.tenant_id, staff_id=context.staff_id, key=key, request_hash=self._hash("CREATE_PRODUCT", None, None, values), values=values)

    async def update_product(self, context: StaffRequestContext, product_id: UUID, expected_version: int, command: UpdateProductCommand, key: str, supplied_fields: set[str]) -> ProductWithInventory:
        values = self._update_values(command, supplied_fields)
        return await self._repository.update_product(tenant_id=context.tenant_id, staff_id=context.staff_id, product_id=product_id, expected_version=expected_version, key=key, request_hash=self._hash("UPDATE_PRODUCT", product_id, expected_version, values), changes=values)

    async def change_status(self, context: StaffRequestContext, product_id: UUID, expected_version: int, status: ProductStatus, reason: str, key: str) -> ProductWithInventory:
        values = {"status": status, "reason": reason}
        return await self._repository.update_product(tenant_id=context.tenant_id, staff_id=context.staff_id, product_id=product_id, expected_version=expected_version, key=key, request_hash=self._hash("CHANGE_PRODUCT_STATUS", product_id, expected_version, values), changes=values, change_type="ACTIVATED" if status == ProductStatus.ACTIVE else "DEACTIVATED")

    async def movements(self, context: StaffRequestContext, product_id: UUID, **filters) -> InventoryMovementPage:
        return await self._repository.list_movements(context.tenant_id, product_id, **filters)

    async def summary(self, context: StaffRequestContext) -> InventorySummary:
        return await self._repository.summary(context.tenant_id)

    async def adjust(self, context: StaffRequestContext, product_id: UUID, expected_version: int, movement_type: ManualInventoryMovementType, quantity: Decimal, reason: str, key: str) -> InventoryAdjustmentResult:
        values = {"movement_type": movement_type, "quantity": quantity, "reason": reason}
        product, movement, replay = await self._repository.adjust_inventory(tenant_id=context.tenant_id, staff_id=context.staff_id, product_id=product_id, expected_version=expected_version, key=key, request_hash=self._hash("ADJUST_INVENTORY", product_id, expected_version, values), movement_type=InventoryMovementType(movement_type.value), quantity=quantity, reason=reason)
        return InventoryAdjustmentResult(balance=product, movement=movement, idempotent=replay)

    def _create_values(self, command: CreateProductCommand) -> dict[str, Any]:
        sku, normalized = normalize_sku(command.sku)
        self._validate_common(command.name, command.currency, command.unit)
        return {**command.model_dump(), "sku": sku, "sku_normalized": normalized, "name": command.name.strip(), "currency": command.currency.upper()}

    def _update_values(self, command: UpdateProductCommand, supplied: set[str]) -> dict[str, Any]:
        values = {name: getattr(command, name) for name in supplied}
        if "sku" in values:
            values["sku"], values["sku_normalized"] = normalize_sku(values["sku"])
        if "name" in values:
            values["name"] = self._name(values["name"])
        if "currency" in values:
            values["currency"] = values["currency"].upper()
            if values["currency"] not in self._currencies:
                raise ValueError("unsupported currency")
        if "unit" in values and values["unit"] not in self._units:
            raise ValueError("unsupported unit")
        return values

    def _validate_common(self, name: str, currency: str, unit: str) -> None:
        self._name(name)
        if currency.upper() not in self._currencies or unit not in self._units:
            raise ValueError("unsupported catalog configuration")

    @staticmethod
    def _name(value: str) -> str:
        result = value.strip()
        if not result or len(result) > 200:
            raise ValueError("invalid product name")
        return result

    @staticmethod
    def _hash(operation: str, resource_id: UUID | None, version: int | None, values: dict[str, Any]) -> str:
        payload = {"operation": operation, "resource_id": str(resource_id) if resource_id else None, "expected_version": version, "input": values}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=lambda value: value.value if hasattr(value, "value") else str(value)).encode()).hexdigest()
