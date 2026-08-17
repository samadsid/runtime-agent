from __future__ import annotations

from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class ProductStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Product(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    price: Decimal
    currency: str = "INR"
    unit: str
    status: ProductStatus = ProductStatus.ACTIVE

    @model_validator(mode="before")
    @classmethod
    def map_legacy_available(cls, value):
        if isinstance(value, dict) and "status" not in value and "available" in value:
            value = dict(value)
            value["status"] = (
                ProductStatus.ACTIVE if value.pop("available") else ProductStatus.INACTIVE
            )
        return value

    @property
    def available(self) -> bool:
        return self.status == ProductStatus.ACTIVE
