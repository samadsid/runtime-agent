from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InventoryReservationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    CONSUMED = "CONSUMED"


class InventoryBalance(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID
    on_hand_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    reserved_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_reserved_quantity(self) -> InventoryBalance:
        if self.reserved_quantity > self.on_hand_quantity:
            raise ValueError("Reserved quantity cannot exceed on-hand quantity.")
        return self

    @property
    def sellable_quantity(self) -> Decimal:
        return self.on_hand_quantity - self.reserved_quantity


class InventoryReservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    order_id: UUID
    product_id: UUID
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    status: InventoryReservationStatus
    created_at: datetime
    released_at: datetime | None = None
    consumed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_timestamp(self) -> InventoryReservation:
        if self.status == InventoryReservationStatus.ACTIVE:
            if self.released_at is not None or self.consumed_at is not None:
                raise ValueError(
                    "An active reservation cannot have a terminal timestamp."
                )
        elif self.status == InventoryReservationStatus.RELEASED:
            if self.released_at is None or self.consumed_at is not None:
                raise ValueError("A released reservation requires only released_at.")
        elif self.consumed_at is None or self.released_at is not None:
            raise ValueError("A consumed reservation requires only consumed_at.")
        return self


class StockShortage(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: UUID
    product_name: str
    requested_quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    sellable_quantity: Decimal = Field(ge=0, allow_inf_nan=False)
    unit: str
