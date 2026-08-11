from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProductVariant(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID

    product_id: UUID

    sku: str

    name: str

    price: Decimal

    stock_quantity: int

    is_active: bool = True
