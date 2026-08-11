from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Product(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    name: str
    price: Decimal
    currency: str = "INR"
    unit: str
    available: bool = True
