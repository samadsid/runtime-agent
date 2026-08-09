from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .order import OrderStatus


class OrderSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    status: OrderStatus
    created_at: datetime
    item_count: int = Field(ge=0)
    total_amount: Decimal = Field(ge=0, allow_inf_nan=False)


class PendingOrderCancellation(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    requested_at: datetime
