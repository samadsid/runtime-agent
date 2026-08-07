from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Inventory(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID

    available_quantity: int

    reserved_quantity: int = 0