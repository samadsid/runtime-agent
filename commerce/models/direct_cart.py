from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .cart import Cart
from .product import Product


class PendingCartProductOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID
    display_name: str
    canonical_unit: str


class PendingCartAddition(BaseModel):
    model_config = ConfigDict(frozen=True)

    options: tuple[PendingCartProductOption, ...]
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    stated_unit: str | None = None
    created_at: datetime
    source_request_id: str


class ProductResolutionKind(str, Enum):
    UNIQUE = "UNIQUE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"


class DirectCartResultKind(str, Enum):
    ADDED = "ADDED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNAVAILABLE = "UNAVAILABLE"
    UNIT_MISMATCH = "UNIT_MISMATCH"


class DirectCartResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: DirectCartResultKind
    product: Product | None = None
    cart: Cart | None = None
    options: tuple[PendingCartProductOption, ...] = ()
    canonical_unit: str | None = None
    idempotent: bool = False
