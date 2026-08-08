from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .product import Product


class CartItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    product: Product
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
